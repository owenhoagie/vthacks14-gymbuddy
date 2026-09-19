"""Replaceable data repositories; live mode never falls back to synthetic data."""

import csv
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol

from api.config import ROOT, Settings, get_settings
from api.models import (
    FACILITY_NAMES,
    FacilityForecast,
    FacilityId,
    ForecastPoint,
    Interval,
    Occupancy,
)

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def demo_anchor(now: datetime) -> datetime:
    return now.astimezone(timezone.utc).replace(
        second=0, microsecond=0, minute=now.astimezone(timezone.utc).minute // 5 * 5
    )


class Repository(Protocol):
    def occupancy(self, now: datetime) -> list[Occupancy]: ...
    def forecast(self, now: datetime) -> list[FacilityForecast]: ...
    def hours(self, now: datetime) -> dict[FacilityId, list[Interval]]: ...


class DemoRepository:
    def __init__(self, path: Path = ROOT / "fixtures" / "demo.json"):
        self.template = json.loads(path.read_text())

    def occupancy(self, now: datetime) -> list[Occupancy]:
        anchor = demo_anchor(now)
        return [
            Occupancy(
                facility_id=f["facility_id"],
                facility_name=FACILITY_NAMES[FacilityId(f["facility_id"])],
                occupancy=f["occupancy"],
                remaining=f["capacity"] - f["occupancy"],
                capacity=f["capacity"],
                occupancy_pct=round(100 * f["occupancy"] / f["capacity"], 2),
                observed_at=anchor,
                source_updated_at=None,
                provenance="demo",
            )
            for f in self.template["facilities"]
        ]

    def forecast(self, now: datetime) -> list[FacilityForecast]:
        anchor = demo_anchor(now)
        result = []
        for f in self.template["facilities"]:
            knots = f["forecast"]
            points = []
            for offset in range(knots[0][0], knots[-1][0] + 1, 5):
                for (x0, y0), (x1, y1) in zip(knots, knots[1:]):
                    if x0 <= offset <= x1:
                        points.append(
                            ForecastPoint(
                                forecast_time=anchor + timedelta(minutes=offset),
                                predicted_occupancy_pct=round(
                                    y0 + (y1 - y0) * (offset - x0) / (x1 - x0), 2
                                ),
                            )
                        )
                        break
            result.append(
                FacilityForecast(
                    facility_id=f["facility_id"],
                    facility_name=FACILITY_NAMES[FacilityId(f["facility_id"])],
                    points=points,
                    generated_at=anchor,
                    observed_at=anchor,
                    confidence="low",
                    provenance="demo",
                )
            )
        return result

    def hours(self, now: datetime) -> dict[FacilityId, list[Interval]]:
        anchor = demo_anchor(now)
        return {
            FacilityId(f["facility_id"]): [
                Interval(
                    start_time=anchor + timedelta(minutes=a), end_time=anchor + timedelta(minutes=b)
                )
                for a, b in f["opening_hours"]
            ]
            for f in self.template["facilities"]
        }


class LocalRepository:
    """Local collector observations are cached, with their original fetch timestamps."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def occupancy(self, now: datetime) -> list[Occupancy]:
        latest: dict[FacilityId, Occupancy] = {}
        try:
            with self.settings.occupancy_csv_path.open(newline="") as source:
                for row in csv.DictReader(source):
                    try:
                        facility = FacilityId(row["facility_id"])
                        observed = datetime.fromisoformat(row["observed_at"].replace("Z", "+00:00"))
                        if observed.tzinfo is None or observed > now + timedelta(minutes=5):
                            continue
                        count, capacity = int(row["occupancy"]), int(row["capacity"])
                        record = Occupancy(
                            facility_id=facility,
                            facility_name=FACILITY_NAMES[facility],
                            occupancy=count,
                            remaining=int(row.get("remaining") or capacity - count),
                            capacity=capacity,
                            occupancy_pct=round(100 * count / capacity, 2),
                            observed_at=observed,
                            source_updated_at=None,
                            provenance="cached",
                            stale=now - observed
                            > timedelta(minutes=self.settings.stale_after_minutes),
                        )
                        if facility not in latest or observed > latest[facility].observed_at:
                            latest[facility] = record
                    except (KeyError, TypeError, ValueError, ZeroDivisionError):
                        logger.warning("Skipping invalid local occupancy row")
        except (OSError, csv.Error):
            logger.info("Local occupancy cache unavailable")
        return [
            latest.get(
                facility,
                Occupancy(facility_id=facility, facility_name=name, provenance="unavailable"),
            )
            for facility, name in FACILITY_NAMES.items()
        ]

    def forecast(self, now: datetime) -> list[FacilityForecast]:
        return [
            FacilityForecast(
                facility_id=f,
                facility_name=name,
                points=[],
                generated_at=None,
                observed_at=None,
                confidence="low",
                provenance="unavailable",
            )
            for f, name in FACILITY_NAMES.items()
        ]

    def hours(self, now: datetime) -> dict[FacilityId, list[Interval]]:
        # Without Gold forecasts there is nothing to recommend. The verified VT
        # hours adapter is wired together with Databricks in the next milestone.
        return {facility: [] for facility in FACILITY_NAMES}


def get_repository() -> Repository:
    settings = get_settings()
    return DemoRepository() if settings.data_mode == "demo" else LocalRepository(settings)
