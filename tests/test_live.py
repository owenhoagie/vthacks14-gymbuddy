from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from api.config import Settings
from api.databricks import DatabricksConfig
from api.live import LiveRepository
from api.models import FacilityForecast, ForecastPoint, Interval, Occupancy, RecommendationRequest
from api.recommendation import recommend

NOW = datetime.now(timezone.utc)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr("api.live.utc_now", lambda: NOW)
    settings = Settings(
        _env_file=None,
        data_mode="live",
        occupancy_csv_path=tmp_path / "raw.csv",
        databricks_host="https://example.com",
        databricks_token="private",
        databricks_sql_warehouse_id="warehouse",
        databricks_catalog="workspace",
    )
    config = DatabricksConfig.from_settings(settings)
    occupancy = [
        Occupancy(
            facility_id="mccomas",
            facility_name="McComas Hall",
            occupancy=30,
            capacity=100,
            remaining=70,
            occupancy_pct=30,
            observed_at=NOW,
            provenance="live",
        )
    ]
    forecast = [
        FacilityForecast(
            facility_id="mccomas",
            facility_name="McComas Hall",
            points=[
                ForecastPoint(forecast_time=NOW + timedelta(minutes=i), predicted_occupancy_pct=30)
                for i in range(0, 241, 5)
            ],
            observed_at=NOW,
            generated_at=NOW,
            confidence="low",
            provenance="live",
        )
    ]
    warehouse = Mock(
        config=config,
        get_occupancy=Mock(return_value=occupancy),
        get_forecast=Mock(return_value=forecast),
    )
    hours = Mock(
        return_value={
            "mccomas": [Interval(start_time=NOW, end_time=NOW + timedelta(hours=4))],
            "war_memorial": [],
        }
    )
    return settings, warehouse, hours


def test_live_refresh_failure_and_restart_preserve_timestamps(setup):
    settings, warehouse, hours = setup
    repo = LiveRepository(settings, warehouse, hours)
    repo.refresh()
    assert repo.occupancy(NOW)[0].provenance == "live"
    assert repo.occupancy(NOW)[1].provenance == "unavailable"
    warehouse.get_forecast.side_effect = RuntimeError("test-secret")
    repo.refresh()
    cached = repo.forecast(NOW)[0]
    assert cached.provenance == "cached"
    assert cached.observed_at == cached.generated_at == NOW
    assert repo.status(NOW).status == "unavailable"
    restored = LiveRepository(settings, warehouse, hours)
    assert restored.forecast(NOW)[0] == cached
    assert restored.forecast(NOW + timedelta(minutes=16))[0].stale


def test_stale_forecast_is_excluded_and_hours_expire(setup):
    settings, warehouse, hours = setup
    repo = LiveRepository(settings, warehouse, hours)
    repo.refresh()
    repo.refresh_hours()
    assert repo.hours(NOW)["mccomas"]
    assert not repo.hours(NOW + timedelta(minutes=15))["mccomas"]
    later = NOW + timedelta(minutes=16)
    result = recommend(
        RecommendationRequest(
            start_time=later, end_time=later + timedelta(hours=3), workout_duration_minutes=75
        ),
        repo.forecast(later),
        hours(),
        later,
        "live",
    )
    assert result.status == "data_unavailable"


def test_no_network_on_reads_and_hours_cached(setup):
    settings, warehouse, hours = setup
    repo = LiveRepository(settings, warehouse, hours)
    repo.refresh_hours()
    repo.refresh_hours()
    assert hours.call_count == 1
    repo.occupancy(NOW)
    repo.forecast(NOW)
    repo.hours(NOW)
    warehouse.get_occupancy.assert_not_called()
    warehouse.get_forecast.assert_not_called()


def test_rejects_demo_recovery_snapshot(setup):
    settings, warehouse, hours = setup
    repo = LiveRepository(settings, warehouse, hours)
    repo.refresh()
    text = repo.cache_path.read_text().replace('"live"', '"demo"')
    repo.cache_path.write_text(text)
    restored = LiveRepository(settings, warehouse, hours)
    assert all(f.provenance == "unavailable" for f in restored.forecast(NOW))


def test_dead_refresh_worker_does_not_claim_live_forever(setup):
    settings, warehouse, hours = setup
    repo = LiveRepository(settings, warehouse, hours)
    repo.refresh()
    assert repo.forecast(NOW + timedelta(minutes=3))[0].provenance == "cached"


def test_newer_local_observation_fallback_does_not_refresh_forecast(setup):
    from collector.run import append_observation
    from tests.test_sync import observation

    settings, warehouse, hours = setup
    repo = LiveRepository(settings, warehouse, hours)
    repo.refresh()
    later = NOW + timedelta(minutes=1)
    append_observation(
        settings.occupancy_csv_path, observation(45) | {"observed_at": later.isoformat()}
    )
    assert repo.occupancy(later)[0].occupancy == 30
    warehouse.get_occupancy.side_effect = RuntimeError("offline")
    repo.refresh()
    assert repo.occupancy(later)[0].occupancy == 45
    assert repo.occupancy(later)[0].provenance == "cached"
    assert repo.forecast(later)[0].observed_at == NOW


def test_serverless_refreshes_during_requests_without_background_threads(setup):
    settings, warehouse, hours = setup
    settings.api_runtime = "serverless"
    repo = LiveRepository(settings, warehouse, hours)
    repo.start()
    assert not repo.threads
    repo.prepare_request()
    repo.prepare_request()
    assert warehouse.get_occupancy.call_count == 1
    assert hours.call_count == 0
    repo.prepare_request(include_hours=True)
    assert hours.call_count == 1
    assert repo.occupancy(NOW)[0].provenance == "live"


def test_serverless_failed_refresh_is_throttled_and_does_not_renew_cache(setup):
    settings, warehouse, hours = setup
    settings.api_runtime = "serverless"
    repo = LiveRepository(settings, warehouse, hours)
    repo.refresh()
    warehouse.get_occupancy.side_effect = RuntimeError("offline")
    repo.prepare_request()
    repo.prepare_request()
    assert warehouse.get_occupancy.call_count == 2
    assert repo.forecast(NOW)[0].provenance == "cached"
    assert repo.forecast(NOW)[0].observed_at == NOW
