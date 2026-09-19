from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from api.models import Interval, RecommendationRequest


def test_openapi_output_types_remain_usable_by_frontend_codegen():
    from api.main import app

    schemas = app.openapi()["components"]["schemas"]
    candidate = schemas["Candidate"]["properties"]
    assert candidate["start_time"]["type"] == "string"
    assert candidate["start_time"]["format"] == "date-time"
    assert candidate["predicted_occupancy_pct"]["type"] == "number"
    assert candidate["facility_id"]["$ref"].endswith("/FacilityId")
    assert schemas["OccupancyResponse"]["properties"]["facilities"]["type"] == "array"


def test_time_inputs_require_offsets_and_serialize_utc():
    interval = Interval(
        start_time="2026-09-19T10:00:00-04:00", end_time="2026-09-19T11:00:00-04:00"
    )
    assert interval.model_dump(mode="json")["start_time"] == "2026-09-19T14:00:00Z"
    with pytest.raises(ValidationError):
        Interval(start_time="2026-09-19T10:00:00", end_time="2026-09-19T11:00:00")


def test_dst_fall_back_interval_compares_instants():
    interval = Interval(
        start_time="2026-11-01T01:30:00-04:00", end_time="2026-11-01T01:15:00-05:00"
    )
    assert interval.end_time - interval.start_time == timedelta(minutes=45)


def test_request_rejects_unbounded_search_and_unknown_facility():
    start = datetime(2026, 9, 19, 17, tzinfo=timezone.utc)
    with pytest.raises(ValidationError):
        RecommendationRequest(start_time=start, end_time=start + timedelta(hours=5))
    with pytest.raises(ValidationError):
        RecommendationRequest(
            start_time=start, end_time=start + timedelta(hours=4), preferred_gyms=["other"]
        )
