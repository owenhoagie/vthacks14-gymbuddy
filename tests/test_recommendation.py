from datetime import datetime, timedelta, timezone

import pytest

from api.models import FacilityForecast, FacilityId, ForecastPoint, Interval, RecommendationRequest
from api.recommendation import average_occupancy, merge_intervals, recommend
from api.repository import DemoRepository

NOW = datetime(2026, 9, 19, 14, tzinfo=timezone.utc)


def interval(a, b):
    return Interval(start_time=NOW + timedelta(minutes=a), end_time=NOW + timedelta(minutes=b))


def request(**kwargs):
    return RecommendationRequest(start_time=NOW, end_time=NOW + timedelta(hours=4), **kwargs)


def forecast(facility="mccomas", value=30, **kwargs):
    return FacilityForecast(
        facility_id=facility,
        facility_name=facility,
        points=[
            ForecastPoint(forecast_time=NOW + timedelta(minutes=i), predicted_occupancy_pct=value)
            for i in range(0, 241, 5)
        ],
        generated_at=NOW,
        observed_at=NOW,
        confidence="low",
        provenance="demo",
        **kwargs,
    )


def test_demo_75minute_scenario_respects_overlapping_blocks():
    repository = DemoRepository()
    unavailable = [interval(0, 45), interval(30, 65), interval(165, 200)]
    result = recommend(
        request(unavailable=unavailable), repository.forecast(NOW), repository.hours(NOW), NOW
    )
    assert result.status == "ok"
    for candidate in [result.recommendation, result.alternative]:
        assert candidate
        assert candidate.end_time - candidate.start_time == timedelta(minutes=75)
        assert all(
            candidate.end_time <= block.start_time or candidate.start_time >= block.end_time
            for block in unavailable
        )
    assert result.recommendation.facility_id != result.alternative.facility_id


def test_merge_overlapping_and_touching_intervals():
    assert merge_intervals(
        [interval(20, 40), interval(0, 20), interval(10, 30), interval(80, 90)]
    ) == [interval(0, 40), interval(80, 90)]


def test_integrates_entire_workout_including_partial_segments():
    data = forecast()
    data.points = [
        ForecastPoint(forecast_time=NOW + timedelta(minutes=i), predicted_occupancy_pct=i * 2)
        for i in range(0, 31, 5)
    ]
    assert average_occupancy(
        data, NOW + timedelta(minutes=2), NOW + timedelta(minutes=27)
    ) == pytest.approx(29)
    assert average_occupancy(data, NOW - timedelta(minutes=1), NOW + timedelta(minutes=5)) is None
    assert average_occupancy(data, NOW, NOW + timedelta(minutes=35)) is None


def test_gap_over_15_minutes_prevents_candidate():
    data = forecast()
    data.points = [
        p
        for p in data.points
        if p.forecast_time not in [NOW + timedelta(minutes=i) for i in (5, 10, 15)]
    ]
    assert average_occupancy(data, NOW, NOW + timedelta(minutes=75)) is None


def test_hours_must_cover_entire_workout_and_unknown_hours_fail_closed():
    data = [forecast()]
    assert recommend(request(), data, {}, NOW).status == "no_available_window"
    assert (
        recommend(request(), data, {FacilityId.mccomas: [interval(0, 60)]}, NOW).status
        == "no_available_window"
    )
    # Adjacent explicit hours are continuous.
    result = recommend(
        request(), data, {FacilityId.mccomas: [interval(0, 40), interval(40, 80)]}, NOW
    )
    assert result.status == "ok"
    assert result.recommendation.start_time == NOW


def test_no_window_when_every_time_blocked():
    assert (
        recommend(
            request(unavailable=[interval(-10, 250)]),
            [forecast()],
            {FacilityId.mccomas: [interval(0, 240)]},
            NOW,
        ).status
        == "no_available_window"
    )


def test_threshold_filter_and_preference_bonus():
    hours = {facility: [interval(0, 240)] for facility in FacilityId}
    result = recommend(
        request(preferred_gyms=[FacilityId.mccomas]),
        [forecast(value=34), forecast("war_memorial", 30)],
        hours,
        NOW,
    )
    assert result.recommendation.facility_id == FacilityId.mccomas
    result = recommend(
        request(preferred_gyms=[FacilityId.mccomas]),
        [forecast(value=41), forecast("war_memorial", 39)],
        hours,
        NOW,
    )
    assert result.recommendation.facility_id == FacilityId.war_memorial
    assert not result.recommendation.exceeds_tolerance
    assert result.alternative.exceeds_tolerance


def test_all_exceed_chooses_least_crowded_with_warning_even_with_preference():
    hours = {facility: [interval(0, 240)] for facility in FacilityId}
    result = recommend(
        request(preferred_gyms=[FacilityId.mccomas]),
        [forecast(value=53), forecast("war_memorial", 50)],
        hours,
        NOW,
    )
    assert result.recommendation.facility_id == FacilityId.war_memorial
    assert result.recommendation.exceeds_tolerance
    assert "Every feasible" in result.warnings[0]


def test_ties_pick_earliest_and_past_starts_are_never_selected():
    result = recommend(
        request(),
        [forecast()],
        {FacilityId.mccomas: [interval(0, 240)]},
        NOW + timedelta(minutes=7),
    )
    assert result.recommendation.start_time == NOW + timedelta(minutes=10)


def test_stale_and_unavailable_forecasts_are_rejected():
    assert (
        recommend(
            request(), [forecast(stale=True)], {FacilityId.mccomas: [interval(0, 240)]}, NOW
        ).status
        == "data_unavailable"
    )
    assert recommend(request(), [], {}, NOW).status == "data_unavailable"


def test_offset_equivalent_time_produces_same_window():
    original = request()
    eastern = timezone(timedelta(hours=-4))
    shifted = original.model_copy(
        update={
            "start_time": original.start_time.astimezone(eastern),
            "end_time": original.end_time.astimezone(eastern),
        }
    )
    hours = {FacilityId.mccomas: [interval(0, 240)]}
    assert (
        recommend(original, [forecast()], hours, NOW).recommendation
        == recommend(shifted, [forecast()], hours, NOW).recommendation
    )
