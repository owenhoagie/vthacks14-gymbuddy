"""Replaceable data repositories; live mode never falls back to synthetic data."""

import csv
import logging
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Protocol

from api.config import Settings, get_settings
from api.demo import DemoRepository as DemoRepository
from api.models import (
    FACILITY_NAMES,
    FacilityForecast,
    FacilityId,
    Interval,
    Occupancy,
)

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Repository(Protocol):
    def occupancy(self, now: datetime) -> list[Occupancy]: ...
    def forecast(self, now: datetime) -> list[FacilityForecast]: ...
    def hours(self, now: datetime) -> dict[FacilityId, list[Interval]]: ...


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


@lru_cache
def get_demo_repository() -> DemoRepository:
    return DemoRepository()


@lru_cache
def get_repository() -> Repository:
    settings = get_settings()
    if settings.data_mode == "demo":
        return get_demo_repository()
    from api.live import LiveRepository

    return LiveRepository(settings)
