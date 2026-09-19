import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from api.config import ROOT, Settings, get_settings
from api.demo import CAPACITIES, EASTERN, DemoRepository, HistoricalProfile, load_history
from api.main import app
from api.models import FacilityId
from api.repository import get_repository
from scripts.generate_demo_history import DAYS, START, evaluate, generate

NOW = datetime(2026, 9, 19, 19, 2, tzinfo=timezone.utc)


def test_history_reproducible_complete_and_explicitly_synthetic(tmp_path):
    path = tmp_path / "history.csv"
    generate(path)
    assert path.read_bytes() == (ROOT / "fixtures/demo-history.csv").read_bytes()
    rows = load_history(path)
    assert len(rows) == DAYS * 96 * 2 == 12096
    assert len({(r["facility_id"], r["at"]) for r in rows}) == len(rows)
    assert max(r["at"] for r in rows) < NOW
    assert all(0 <= r["pct"] <= 100 for r in rows)


def test_seasonal_model_is_fit_from_history_not_a_hardcoded_curve():
    rows = load_history()
    profile = HistoricalProfile(rows)
    changed = HistoricalProfile([row | {"pct": 10.0} for row in rows])
    for facility in CAPACITIES:
        assert changed.predict(facility, NOW) == pytest.approx(10)
        assert profile.predict(facility, NOW) > 30
        evening = datetime(2026, 9, 21, 18, tzinfo=EASTERN)
        overnight = evening.replace(hour=3)
        assert profile.predict(facility, evening) > profile.predict(facility, overnight) + 30


def test_heldout_week_beats_constant_mean_on_synthetic_data_only():
    report = evaluate(load_history())
    assert report == json.loads((ROOT / "fixtures/demo.json").read_text())
    assert report["training_days"] == 56 and report["holdout_days"] == 7
    for result in report["metrics"].values():
        assert (
            result["seasonal_mae_percentage_points"]
            < result["constant_mean_mae_percentage_points"] / 2
        )


def test_training_excludes_holdout_week():
    cutoff = START + timedelta(days=56)
    rows = load_history()
    training = [row for row in rows if row["at"] < cutoff]
    assert len(training) == 56 * 96 * 2
    original = HistoricalProfile(training)
    mutated = [row | {"pct": 99.0} if row["at"] >= cutoff else row for row in rows]
    again = HistoricalProfile([row for row in mutated if row["at"] < cutoff])
    assert original.means == again.means


@pytest.mark.parametrize(
    "now",
    [
        NOW,
        datetime(2026, 11, 1, 5, 55, tzinfo=timezone.utc),
        datetime(2027, 3, 14, 6, 55, tzinfo=timezone.utc),
        datetime(2026, 9, 21, 3, 55, tzinfo=timezone.utc),
    ],
)
def test_demo_forecasts_are_bounded_repeatable_and_cover_next_four_hours(now):
    repo = DemoRepository()
    observations = {row.facility_id: row for row in repo.occupancy(now)}
    forecasts = repo.forecast(now)
    assert forecasts == repo.forecast(now)
    for forecast in forecasts:
        assert forecast.provenance == "demo" and forecast.confidence == "low"
        assert len(forecast.points) == 50
        assert forecast.points[-1].forecast_time >= now + timedelta(hours=4)
        assert forecast.points[0].predicted_occupancy_pct == pytest.approx(
            observations[forecast.facility_id].occupancy_pct, abs=0.01
        )
        assert all(0 <= p.predicted_occupancy_pct <= 100 for p in forecast.points)
        assert all(
            b.forecast_time - a.forecast_time == timedelta(minutes=5)
            for a, b in zip(forecast.points, forecast.points[1:])
        )


def test_day_of_week_and_timezone_are_part_of_prediction():
    model = HistoricalProfile(load_history())
    eastern = datetime(2026, 9, 19, 15, tzinfo=EASTERN)
    assert model.predict(FacilityId.mccomas, eastern) == model.predict(
        FacilityId.mccomas, eastern.astimezone(timezone.utc)
    )
    assert model.predict(FacilityId.mccomas, eastern) != model.predict(
        FacilityId.mccomas, eastern + timedelta(days=2)
    )


def test_demo_request_bypasses_live_queries_and_never_changes_default(monkeypatch):
    class Offline:
        def prepare_request(self, **kwargs):
            raise RuntimeError("A demo request must never query the warehouse")

    monkeypatch.setattr("api.main.utc_now", lambda: NOW)
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, data_mode="live")
    app.dependency_overrides[get_repository] = Offline
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            for endpoint in ["health", "occupancy", "forecast"]:
                response = client.get("/" + endpoint + "?demo=true")
                assert response.status_code == 200
                assert response.json()["data_mode"] == "demo"
            request = {
                "start_time": NOW.isoformat(),
                "end_time": (NOW + timedelta(hours=4)).isoformat(),
                "workout_duration_minutes": 75,
            }
            result = client.post("/recommend?demo=true", json=request).json()
            assert result["status"] == "ok"
            assert result["recommendation"]["provenance"] == "demo"
            # The explicit demo request does not change other visitors' live requests.
            assert client.get("/occupancy").status_code == 500
            assert client.get("/occupancy?demo=invalid").status_code == 422
    finally:
        app.dependency_overrides.clear()
