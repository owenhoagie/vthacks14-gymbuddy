"""Fail-closed adapter for Virginia Tech's public facility-hours service."""

import logging
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

from api.models import FacilityId, Interval

EASTERN = ZoneInfo("America/New_York")
HOURS_URL = "https://apps.students.vt.edu/rshours/Api/NonRestricted/UnitsOpenOnDay/Date"
UNITS = {"1": FacilityId.mccomas, "2": FacilityId.war_memorial}
log = logging.getLogger(__name__)


class HoursSchedule(dict):
    """Open intervals plus dates with a verified schedule, including explicit closures."""

    def __init__(self, *args, known_days=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.known_days = set(known_days)


def opening_status(schedule, facility, now):
    intervals = sorted(schedule.get(facility, []), key=lambda i: i.start_time)
    active = next((i for i in intervals if i.start_time <= now < i.end_time), None)
    upcoming = next((i for i in intervals if i.start_time > now), None)
    known = (facility, now.astimezone(EASTERN).date()) in getattr(schedule, "known_days", set())
    return {
        "opening_status": "open" if active else "closed" if known else "unknown",
        "opens_at": upcoming.start_time if upcoming else None,
        "closes_at": active.end_time if active else None,
    }


def parse_hours(payload: list, day: date) -> dict[FacilityId, list[Interval]]:
    """Unknown, malformed, or explicitly closed facilities get no open intervals."""
    result = HoursSchedule({facility: [] for facility in UNITS.values()})
    if not isinstance(payload, list):
        raise ValueError("Unexpected VT hours response")
    for unit in payload:
        if not isinstance(unit, dict) or str(unit.get("id")) not in UNITS:
            continue
        facility = UNITS[str(unit["id"])]
        try:
            hours = unit["hours"]
            if not isinstance(hours, list):
                raise ValueError("Invalid hours list")
            intervals = []
            matched = False
            for row in hours:
                if date.fromisoformat(row["start"]) > day or date.fromisoformat(row["end"]) < day:
                    continue
                matched = True
                text = f"{row.get('title', '')} {row.get('label', '')}".lower()
                if "closed" in text:
                    intervals = []
                    break
                opens = datetime.combine(day, time.fromisoformat(row["open_time"]), EASTERN)
                closes = datetime.combine(day, time.fromisoformat(row["close_time"]), EASTERN)
                if closes == opens:
                    raise ValueError("Ambiguous equal opening and closing times")
                if closes < opens:
                    closes += timedelta(days=1)
                intervals.append(
                    Interval(
                        start_time=opens.astimezone(timezone.utc),
                        end_time=closes.astimezone(timezone.utc),
                    )
                )
            result[facility] = intervals
            if matched:
                result.known_days.add((facility, day))
        except (ValueError, KeyError, TypeError, AttributeError):
            log.warning("Ignoring invalid hours for %s on %s", facility.value, day)
            result[facility] = []
            result.known_days.discard((facility, day))
    return result


def get_hours(
    start: datetime, end: datetime, client: httpx.Client | None = None
) -> dict[FacilityId, list[Interval]]:
    if start.utcoffset() is None or end.utcoffset() is None or end <= start:
        raise ValueError("Hours bounds must be ordered timezone-aware datetimes")
    if end - start > timedelta(days=7):
        raise ValueError("Hours bounds must not exceed seven days")
    result = HoursSchedule({facility: [] for facility in UNITS.values()})
    own_client = client is None
    client = client or httpx.Client(timeout=15, follow_redirects=True)
    # Include yesterday to preserve any overnight opening interval crossing midnight.
    day = start.astimezone(EASTERN).date() - timedelta(days=1)
    last_day = end.astimezone(EASTERN).date()
    try:
        while day <= last_day:
            try:
                response = client.get(f"{HOURS_URL}/{day.isoformat()}")
                response.raise_for_status()
                parsed = parse_hours(response.json(), day)
                result.known_days.update(parsed.known_days)
                for facility, intervals in parsed.items():
                    result[facility].extend(
                        i for i in intervals if i.end_time > start and i.start_time < end
                    )
            except (httpx.HTTPError, ValueError):
                log.warning("VT hours unavailable for %s; no intervals assumed", day)
            day += timedelta(days=1)
    finally:
        if own_client:
            client.close()
    return result
