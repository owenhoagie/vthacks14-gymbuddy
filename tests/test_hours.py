from datetime import date, datetime, timezone

import httpx
import pytest

from api.hours import get_hours, parse_hours
from api.models import FacilityId


def payload(day="2026-09-19", opens="08:00:01", closes="20:00:00"):
    return [
        {
            "id": "1",
            "name": "McComas",
            "hours": [
                {
                    "start": day,
                    "end": day,
                    "open_time": opens,
                    "close_time": closes,
                    "title": "Regular Hours",
                    "label": "Regular Hours",
                }
            ],
        }
    ]


def test_real_hours_shape_normalizes_eastern_to_utc_and_unknown_closed():
    result = parse_hours(payload(), date(2026, 9, 19))
    interval = result[FacilityId.mccomas][0]
    assert interval.start_time == datetime(2026, 9, 19, 12, 0, 1, tzinfo=timezone.utc)
    assert interval.end_time == datetime(2026, 9, 20, 0, 0, tzinfo=timezone.utc)
    assert result[FacilityId.war_memorial] == []


def test_winter_offset_and_overnight():
    interval = parse_hours(payload("2026-12-19", "22:00:00", "02:00:00"), date(2026, 12, 19))[
        FacilityId.mccomas
    ][0]
    assert interval.start_time == datetime(2026, 12, 20, 3, tzinfo=timezone.utc)
    assert interval.end_time == datetime(2026, 12, 20, 7, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "row",
    [
        {"title": "Closed"},
        {"open_time": "invalid"},
        {
            "start": "2026-09-19",
            "end": "2026-09-19",
            "open_time": "00:00:00",
            "close_time": "00:00:00",
        },
    ],
)
def test_closed_or_malformed_fails_closed(row):
    assert parse_hours([{"id": "1", "hours": [row]}], date(2026, 9, 19))[FacilityId.mccomas] == []


def test_transport_failure_does_not_assume_open_hours():
    client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(503)))
    result = get_hours(
        datetime(2026, 9, 19, 17, tzinfo=timezone.utc),
        datetime(2026, 9, 19, 21, tzinfo=timezone.utc),
        client=client,
    )
    assert all(not intervals for intervals in result.values())


def test_get_hours_filters_to_requested_horizon_and_preserves_overnight():
    def handler(request):
        day = request.url.path.split("/")[-1]
        return httpx.Response(200, json=payload(day, "22:00:00", "02:00:00"))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = get_hours(
        datetime(2026, 9, 20, 4, tzinfo=timezone.utc),
        datetime(2026, 9, 20, 5, tzinfo=timezone.utc),
        client,
    )
    assert len(result[FacilityId.mccomas]) == 1
    assert result[FacilityId.mccomas][0].start_time == datetime(2026, 9, 20, 2, tzinfo=timezone.utc)


def test_open_closed_and_unknown_are_distinct_at_boundaries():
    from api.hours import opening_status

    schedule = parse_hours(payload(), date(2026, 9, 19))
    before = datetime(2026, 9, 19, 11, tzinfo=timezone.utc)
    status = opening_status(schedule, FacilityId.mccomas, before)
    assert status["opening_status"] == "closed"
    assert status["opens_at"] == schedule[FacilityId.mccomas][0].start_time
    assert opening_status(schedule, FacilityId.war_memorial, before)["opening_status"] == "unknown"
    interval = schedule[FacilityId.mccomas][0]
    assert (
        opening_status(schedule, FacilityId.mccomas, interval.start_time)["opening_status"]
        == "open"
    )
    assert (
        opening_status(schedule, FacilityId.mccomas, interval.start_time)["closes_at"]
        == interval.end_time
    )
    assert (
        opening_status(schedule, FacilityId.mccomas, interval.end_time)["opening_status"]
        == "closed"
    )


def test_explicit_closure_is_known_but_missing_or_invalid_hours_are_unknown():
    from api.hours import opening_status

    now = datetime(2026, 9, 19, 14, tzinfo=timezone.utc)
    data = payload()
    data[0]["hours"][0]["title"] = "Closed"
    schedule = parse_hours(data, date(2026, 9, 19))
    assert opening_status(schedule, FacilityId.mccomas, now)["opening_status"] == "closed"
    data[0]["hours"] = []
    assert (
        opening_status(parse_hours(data, now.date()), FacilityId.mccomas, now)["opening_status"]
        == "unknown"
    )
    malformed = parse_hours(payload(opens="invalid"), now.date())
    assert opening_status(malformed, FacilityId.mccomas, now)["opening_status"] == "unknown"


def test_old_closure_does_not_override_todays_open_hours():
    data = payload()
    data[0]["hours"].insert(0, {"start": "2026-09-18", "end": "2026-09-18", "title": "Closed"})
    assert parse_hours(data, date(2026, 9, 19))[FacilityId.mccomas]


def test_successful_fetch_preserves_known_closed_status():
    from api.hours import opening_status

    def handler(request):
        data = payload(request.url.path.split("/")[-1])
        data[0]["hours"][0]["title"] = "Closed"
        return httpx.Response(200, json=data)

    start = datetime(2026, 9, 19, 14, tzinfo=timezone.utc)
    end = datetime(2026, 9, 19, 18, tzinfo=timezone.utc)
    schedule = get_hours(start, end, httpx.Client(transport=httpx.MockTransport(handler)))
    assert opening_status(schedule, FacilityId.mccomas, start)["opening_status"] == "closed"
    assert opening_status(schedule, FacilityId.war_memorial, start)["opening_status"] == "unknown"
