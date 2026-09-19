import csv
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from api.config import Settings, get_settings
from api.main import app
from api.models import RecommendationRequest
from api.repository import DemoRepository, LocalRepository, get_repository

NOW = datetime(2026, 9, 19, 14, tzinfo=timezone.utc)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr("api.main.utc_now", lambda: NOW)
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, data_mode="demo")
    app.dependency_overrides[get_repository] = DemoRepository
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


def payload():
    return {
        "start_time": NOW.isoformat(),
        "end_time": (NOW + timedelta(hours=4)).isoformat(),
        "workout_duration_minutes": 75,
        "unavailable": [],
        "preferred_gyms": [],
        "crowd_tolerance": "low",
    }


def test_all_endpoints_without_credentials(client):
    health = client.get("/health").json()
    assert health["status"] == "ok"
    assert health["integrations"]["gemini"]["status"] == "not_configured"
    occupancy = client.get("/occupancy").json()
    assert len(occupancy["facilities"]) == 2
    assert all(
        f["provenance"] == "demo" and f["source_updated_at"] is None
        for f in occupancy["facilities"]
    )
    assert len(client.get("/forecast").json()["facilities"]) == 2
    for _ in range(3):
        response = client.post("/recommend", json=payload())
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert response.json()["recommendation"]["start_time"].endswith("Z")


@pytest.mark.parametrize(
    "changes",
    [
        {"start_time": "2026-09-19T14:00:00"},
        {"end_time": "2026-09-19T14:00:00Z"},
        {"end_time": "2026-09-20T14:00:00Z"},
        {"workout_duration_minutes": 0},
        {"preferred_gyms": ["not_a_gym"]},
        {
            "unavailable": [
                {"start_time": "2026-09-19T14:00:00", "end_time": "2026-09-19T15:00:00Z"}
            ]
        },
    ],
)
def test_validation_uses_error_envelope(client, changes):
    response = client.post("/recommend", json=payload() | changes)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_forecast_filters_and_validation(client):
    result = client.get(
        "/forecast",
        params={
            "facility_id": "mccomas",
            "start_time": "2026-09-19T15:00:00Z",
            "end_time": "2026-09-19T15:30:00Z",
        },
    )
    assert result.status_code == 200
    assert len(result.json()["facilities"]) == 1
    assert len(result.json()["facilities"][0]["points"]) == 7
    assert client.get("/forecast", params={"start_time": "2026-09-19T15:00:00"}).status_code == 422
    assert client.get(
        "/forecast",
        params={"start_time": "2026-09-19T15:00:00Z", "end_time": "2026-09-19T14:00:00Z"},
    ).json()["error"]


def test_http_and_unexpected_errors_are_safe(client):
    assert client.get("/missing").json()["error"]["code"] == "http_error"

    class Broken:
        def occupancy(self, now):
            raise ValueError("secret-token-do-not-leak")

    app.dependency_overrides[get_repository] = Broken
    response = client.get("/occupancy")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "secret-token" not in response.text


def test_live_never_substitutes_demo_and_configured_integrations_are_honest(client, tmp_path):
    settings = Settings(
        _env_file=None,
        data_mode="live",
        occupancy_csv_path=tmp_path / "missing.csv",
        gemini_api_key="private-secret",
        gemini_model="future-model",
        databricks_host="private-host",
        databricks_token="private-token",
        databricks_sql_warehouse_id="warehouse",
        databricks_catalog="catalog",
    )
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_repository] = lambda: LocalRepository(settings)
    health = client.get("/health")
    assert health.json()["integrations"]["databricks"]["status"] == "unavailable"
    assert "private" not in health.text
    assert all(
        f["provenance"] == "unavailable" for f in client.get("/occupancy").json()["facilities"]
    )
    assert all(f["points"] == [] for f in client.get("/forecast").json()["facilities"])
    assert client.post("/recommend", json=payload()).json()["status"] == "data_unavailable"


def test_cache_timestamp_never_refreshes_and_bad_rows_do_not_hide_previous_data(tmp_path):
    path = tmp_path / "observations.csv"
    observed = NOW - timedelta(hours=1)
    with path.open("w", newline="") as source:
        writer = csv.DictWriter(
            source, fieldnames=["facility_id", "observed_at", "occupancy", "capacity", "remaining"]
        )
        writer.writeheader()
        writer.writerow(
            {
                "facility_id": "mccomas",
                "observed_at": observed.isoformat(),
                "occupancy": 25,
                "capacity": 100,
                "remaining": 75,
            }
        )
        writer.writerow(
            {
                "facility_id": "mccomas",
                "observed_at": NOW.isoformat(),
                "occupancy": "broken",
                "capacity": 100,
            }
        )
    repository = LocalRepository(Settings(_env_file=None, occupancy_csv_path=path))
    first = repository.occupancy(NOW)[0]
    second = repository.occupancy(NOW + timedelta(hours=1))[0]
    assert first.observed_at == second.observed_at == observed
    assert first.stale and second.stale
    assert first.occupancy == 25
    assert first.provenance == "cached"


def test_naive_contract_rejected():
    with pytest.raises(ValueError):
        RecommendationRequest(
            start_time=datetime(2026, 9, 19, 14), end_time=NOW + timedelta(hours=1)
        )
