"""Deterministic scheduling using full-workout forecast integration."""

import math
from datetime import datetime, timedelta, timezone

from api.models import (
    Candidate,
    FacilityForecast,
    FacilityId,
    Interval,
    RecommendationRequest,
    RecommendationResponse,
)

THRESHOLDS = {"low": 40, "medium": 65, "high": 85}


def merge_intervals(intervals: list[Interval]) -> list[Interval]:
    merged: list[Interval] = []
    for item in sorted(intervals, key=lambda interval: interval.start_time):
        if merged and item.start_time <= merged[-1].end_time:
            merged[-1] = Interval(
                start_time=merged[-1].start_time, end_time=max(merged[-1].end_time, item.end_time)
            )
        else:
            merged.append(item)
    return merged


def average_occupancy(forecast: FacilityForecast, start: datetime, end: datetime) -> float | None:
    """Integrate piecewise-linear points; never extrapolate or bridge missing data."""
    points = sorted(forecast.points, key=lambda p: p.forecast_time)
    if len(points) < 2 or start < points[0].forecast_time or end > points[-1].forecast_time:
        return None
    total, covered = 0.0, 0.0
    for left, right in zip(points, points[1:]):
        a, b = max(start, left.forecast_time), min(end, right.forecast_time)
        if b <= a:
            continue
        segment = (right.forecast_time - left.forecast_time).total_seconds()
        if segment <= 0 or segment > 15 * 60:
            return None
        slope = (right.predicted_occupancy_pct - left.predicted_occupancy_pct) / segment
        v0 = left.predicted_occupancy_pct + slope * (a - left.forecast_time).total_seconds()
        v1 = left.predicted_occupancy_pct + slope * (b - left.forecast_time).total_seconds()
        seconds = (b - a).total_seconds()
        total += (v0 + v1) / 2 * seconds
        covered += seconds
    duration = (end - start).total_seconds()
    if duration <= 0 or abs(covered - duration) > 0.001:
        return None
    return total / duration


def recommend(
    request: RecommendationRequest,
    forecasts: list[FacilityForecast],
    hours: dict[FacilityId, list[Interval]],
    now: datetime,
    data_mode: str = "demo",
) -> RecommendationResponse:
    usable = [f for f in forecasts if f.points and f.provenance != "unavailable" and not f.stale]
    base = {"generated_at": now, "data_mode": data_mode}
    if not usable:
        return RecommendationResponse(
            status="data_unavailable",
            explanation="Forecast data is unavailable or stale. Collect observations and connect the Databricks forecast pipeline before requesting live recommendations.",
            **base,
        )
    blocked = merge_intervals(request.unavailable)
    start = max(request.start_time, now)
    start = datetime.fromtimestamp(math.ceil(start.timestamp() / 300) * 300, tz=timezone.utc)
    duration = timedelta(minutes=request.workout_duration_minutes)
    candidates: list[Candidate] = []
    threshold = THRESHOLDS[request.crowd_tolerance]
    while start + duration <= request.end_time:
        end = start + duration
        if not any(start < interval.end_time and end > interval.start_time for interval in blocked):
            for forecast in usable:
                if not any(
                    start >= interval.start_time and end <= interval.end_time
                    for interval in merge_intervals(hours.get(forecast.facility_id, []))
                ):
                    continue
                average = average_occupancy(forecast, start, end)
                if average is not None:
                    candidates.append(
                        Candidate(
                            facility_id=forecast.facility_id,
                            facility_name=forecast.facility_name,
                            start_time=start,
                            end_time=end,
                            predicted_occupancy_pct=average,
                            confidence=forecast.confidence,
                            provenance=forecast.provenance,
                            exceeds_tolerance=average > threshold,
                        )
                    )
        start += timedelta(minutes=5)
    if not candidates:
        return RecommendationResponse(
            status="no_available_window",
            explanation="No complete workout fits your availability, known opening hours, and forecast coverage. Try a shorter workout or fewer unavailable blocks.",
            **base,
        )
    within_tolerance = [candidate for candidate in candidates if not candidate.exceeds_tolerance]
    pool = within_tolerance or candidates

    # When all windows exceed tolerance the explicit least-crowded fallback wins,
    # without allowing a preference bonus to choose a more crowded workout.
    def rank(candidate: Candidate):
        bonus = 5 if within_tolerance and candidate.facility_id in request.preferred_gyms else 0
        return (
            candidate.predicted_occupancy_pct - bonus,
            candidate.start_time,
            candidate.facility_id.value,
        )

    ordered = sorted(pool, key=rank)
    primary = ordered[0]
    alternative = next(
        (candidate for candidate in ordered if candidate.facility_id != primary.facility_id), None
    )
    if alternative is None:
        alternative = next(
            (
                candidate
                for candidate in sorted(candidates, key=rank)
                if candidate.facility_id != primary.facility_id
            ),
            None,
        )
    if alternative is None:
        alternative = next(
            (
                candidate
                for candidate in ordered[1:]
                if candidate.start_time >= primary.end_time
                or candidate.end_time <= primary.start_time
            ),
            None,
        )
    warnings = []
    if not within_tolerance:
        warnings.append(
            f"Every feasible workout exceeds your {threshold}% crowd tolerance; this is the least crowded available option."
        )
    if alternative and alternative.exceeds_tolerance:
        warnings.append(f"The alternative exceeds your {threshold}% crowd tolerance.")
    if data_mode == "demo":
        warnings.append(
            "Synthetic demo forecasts and opening hours; this is not live gym guidance."
        )
    explanation = (
        f"{primary.facility_name} averages {primary.predicted_occupancy_pct:.0f}% occupancy across your entire "
        f"{request.workout_duration_minutes}-minute workout. The full window fits your availability and known opening hours."
    )
    if within_tolerance and primary.facility_id in request.preferred_gyms:
        explanation += " Your gym preference contributed a five-point ranking bonus."
    return RecommendationResponse(
        status="ok",
        recommendation=primary,
        alternative=alternative,
        explanation=explanation,
        warnings=warnings,
        **base,
    )
