"""Regenerate checked-in synthetic API examples, never real collector storage."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from api.models import ForecastResponse, Interval, OccupancyResponse, RecommendationRequest
from api.recommendation import recommend
from api.repository import DemoRepository


def main():
    # Fixed reference: September 19, 2026, 1 PM Eastern, for reproducible examples.
    now = datetime(2026, 9, 19, 17, tzinfo=timezone.utc)
    repository = DemoRepository()
    request = RecommendationRequest(
        start_time=now,
        end_time=now + timedelta(hours=4),
        unavailable=[
            Interval(start_time=now - timedelta(hours=3), end_time=now - timedelta(hours=1)),
            Interval(
                start_time=now + timedelta(hours=3), end_time=now + timedelta(hours=4, minutes=15)
            ),
        ],
        workout_duration_minutes=75,
        preferred_gyms=["mccomas"],
        crowd_tolerance="low",
    )
    examples = {
        "occupancy": OccupancyResponse(facilities=repository.occupancy(now), data_mode="demo"),
        "forecast": ForecastResponse(facilities=repository.forecast(now), data_mode="demo"),
        "recommendation-request": request,
        "recommendation-response": recommend(
            request, repository.forecast(now), repository.hours(now), now
        ),
    }
    destination = Path(__file__).resolve().parents[1] / "fixtures"
    for name, value in examples.items():
        (destination / f"{name}.json").write_text(
            json.dumps(value.model_dump(mode="json"), indent=2) + "\n"
        )
    print("Regenerated synthetic API examples in fixtures/; real occupancy files unchanged.")


if __name__ == "__main__":
    main()
