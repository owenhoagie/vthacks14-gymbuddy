import csv
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import httpx
import pytest

from api.config import Settings
from api.live import LiveRepository
from api.models import Interval, RecommendationRequest
from api.recommendation import recommend
from collector.fallback import publish
from collector.run import append_observation
from scripts.cloud_collect import run
from tests.test_sync import observation


def build(tmp_path, counts=(10, 50, 90)):
    now = datetime.now(timezone.utc)
    source, history, snapshot = [tmp_path / n for n in ("raw.csv", "history.csv", "snapshot.json")]
    for i, count in enumerate(counts):
        append_observation(
            source,
            observation(count)
            | {"observed_at": (now - timedelta(minutes=(len(counts) - i - 1) * 5)).isoformat()},
        )
    publish(source, history, snapshot)
    return now, source, history, snapshot


@pytest.mark.parametrize("counts,direction", [((10, 50, 90), 1), ((90, 50, 10), -1)])
def test_real_history_forecast_caps_dedupe_and_timestamps(tmp_path, counts, direction):
    now, source, history, path = build(tmp_path, counts)
    publish(source, history, path)
    assert len(list(csv.DictReader(history.open()))) == 3
    data = json.loads(path.read_text())
    forecast = data["forecast"][0]
    assert datetime.fromisoformat(forecast["observed_at"]) == now
    assert data["occupancy"][0]["source_updated_at"] is None
    assert forecast["forecast_source"] == "collector_fallback"
    assert forecast["confidence"] == "low"
    assert len(forecast["points"]) == 49
    values = [p["predicted_occupancy_pct"] for p in forecast["points"]]
    assert values[1] - values[0] == direction * 1.25
    assert all(0 <= value <= 100 for value in values)


def test_cold_start_is_flat_and_skipped_warehouse_retains_outbox(tmp_path, monkeypatch):
    _, source, history, path = build(tmp_path, (25,))
    assert all(
        p["predicted_occupancy_pct"] == 25
        for p in json.loads(path.read_text())["forecast"][0]["points"]
    )
    monkeypatch.setattr("scripts.cloud_collect.collect_once", lambda *a, **k: (0, 0))
    warehouse = Mock()
    assert run(source, warehouse, fallback_dir=tmp_path, skip_warehouse=True) == 0
    assert len(list(csv.DictReader(source.open()))) == 1
    warehouse.merge.assert_not_called()


def test_fallback_read_never_calls_warehouse_and_stale_data_cannot_recommend(tmp_path, monkeypatch):
    now, _, _, path = build(tmp_path)
    settings = Settings(
        _env_file=None,
        data_mode="live",
        live_data_source="collector_fallback",
        occupancy_csv_path=tmp_path / "api.csv",
    )
    repo = LiveRepository(settings)
    warehouse = Mock(side_effect=AssertionError("warehouse must stay paused"))
    repo.warehouse.get_occupancy = warehouse
    monkeypatch.setattr(
        "api.live.httpx.get",
        lambda *a, **k: httpx.Response(
            200, content=path.read_bytes(), request=httpx.Request("GET", "https://example.com")
        ),
    )
    repo.refresh()
    original = repo.forecast(now)[0]
    assert original.forecast_source == "collector_fallback"
    assert original.provenance == "cached"
    assert repo.status(now).status != "ready"
    warehouse.assert_not_called()
    later = now + timedelta(minutes=16)
    forecasts = repo.forecast(later)
    assert forecasts[0].stale
    request = RecommendationRequest(
        start_time=later, end_time=later + timedelta(hours=3), workout_duration_minutes=75
    )
    assert (
        recommend(
            request,
            forecasts,
            {"mccomas": [Interval(start_time=later, end_time=later + timedelta(hours=3))]},
            later,
            "live",
        ).status
        == "data_unavailable"
    )
    monkeypatch.setattr("api.live.httpx.get", Mock(side_effect=RuntimeError("offline")))
    repo.refresh()
    restored = LiveRepository(settings)
    assert restored.forecast(now)[0].observed_at == original.observed_at
    assert restored.forecast(now)[0].generated_at == original.generated_at
