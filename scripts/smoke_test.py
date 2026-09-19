"""Exercise the running baseplate, including three identical recommendation requests."""

import argparse
from datetime import datetime, timedelta, timezone

import httpx

from api.models import ForecastResponse, HealthResponse, OccupancyResponse, RecommendationResponse


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8000")
    args = parser.parse_args()
    with httpx.Client(base_url=args.url, timeout=15) as client:
        health_response = client.get("/health")
        health_response.raise_for_status()
        health = HealthResponse.model_validate(health_response.json())
        occupancy_response = client.get("/occupancy")
        occupancy_response.raise_for_status()
        occupancy = OccupancyResponse.model_validate(occupancy_response.json())
        assert len(occupancy.facilities) == 2
        forecast_response = client.get("/forecast")
        forecast_response.raise_for_status()
        forecast = ForecastResponse.model_validate(forecast_response.json())
        assert len(forecast.facilities) == 2
        # Relative blocks keep the known-good synthetic scenario runnable at any hour.
        now = datetime.now(timezone.utc)
        start = datetime.fromtimestamp((int(now.timestamp()) // 300 + 1) * 300, timezone.utc)
        payload = {
            "start_time": start.isoformat(),
            "end_time": (start + timedelta(hours=4)).isoformat(),
            "unavailable": [
                {
                    "start_time": start.isoformat(),
                    "end_time": (start + timedelta(minutes=30)).isoformat(),
                }
            ],
            "workout_duration_minutes": 75,
            "preferred_gyms": ["mccomas"],
            "crowd_tolerance": "low",
        }
        previous = None
        for run in range(3):
            response = client.post("/recommend", json=payload)
            response.raise_for_status()
            result = RecommendationResponse.model_validate(response.json())
            if health.data_mode == "demo":
                assert result.status == "ok", result
                assert result.recommendation.provenance == "demo"
                assert result.recommendation.start_time >= start + timedelta(minutes=30)
                assert (
                    result.recommendation.end_time - result.recommendation.start_time
                    == timedelta(minutes=75)
                )
                candidate = result.recommendation.model_dump(mode="json")
                assert previous is None or candidate == previous
                previous = candidate
            print(f"Recommendation {run + 1}: {result.status}")
        invalid = client.post("/recommend", json={**payload, "start_time": "2026-09-19T10:00:00"})
        assert invalid.status_code == 422
        assert invalid.json()["error"]["code"]
        print(f"PASS: API contracts, validation, and repeated scenario ({health.data_mode} mode)")


if __name__ == "__main__":
    main()
