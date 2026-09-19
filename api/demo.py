"""Forecast from explicitly synthetic history. Never reads or writes live storage."""

import csv
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from zoneinfo import ZoneInfo

from api.config import ROOT
from api.models import (
    FACILITY_NAMES,
    FacilityForecast,
    FacilityId,
    ForecastPoint,
    Interval,
    Occupancy,
)

EASTERN = ZoneInfo("America/New_York")
HISTORY_PATH = ROOT / "fixtures" / "demo-history.csv"
CAPACITIES = {FacilityId.mccomas: 600, FacilityId.war_memorial: 1200}


def load_history(path: Path = HISTORY_PATH) -> list[dict]:
    rows = []
    with path.open(newline="") as source:
        for row in csv.DictReader(source):
            if row["provenance"] != "synthetic":
                raise ValueError("Demo history must be explicitly synthetic")
            instant = datetime.fromisoformat(row["observed_at"])
            if instant.tzinfo is None:
                raise ValueError("History timestamps must include timezone")
            pct = float(row["occupancy_pct"])
            if not 0 <= pct <= 100:
                raise ValueError("History percentage out of bounds")
            rows.append({"facility_id": FacilityId(row["facility_id"]), "at": instant, "pct": pct})
    if not rows:
        raise ValueError("Demo history is empty")
    return rows


class HistoricalProfile:
    """Means by gym, Eastern weekday, and quarter-hour, smoothed over adjacent slots."""

    def __init__(self, rows: list[dict]):
        buckets = defaultdict(list)
        self.latest = {}
        for row in sorted(rows, key=lambda r: r["at"]):
            local = row["at"].astimezone(EASTERN)
            key = (row["facility_id"], local.weekday(), local.hour * 4 + local.minute // 15)
            buckets[key].append(row["pct"])
            self.latest[key] = row["pct"]
        if len(buckets) != len(CAPACITIES) * 7 * 96:
            raise ValueError("History must cover every facility, weekday and quarter-hour")
        self.means = {key: mean(values) for key, values in buckets.items()}

    def _slot(self, facility, weekday, slot):
        def value(offset):
            total = weekday * 96 + slot + offset
            return self.means[(facility, (total // 96) % 7, total % 96)]

        return 0.25 * value(-1) + 0.5 * value(0) + 0.25 * value(1)

    def predict(self, facility: FacilityId, at: datetime) -> float:
        local = at.astimezone(EASTERN)
        slot = local.hour * 4 + local.minute // 15
        fraction = (local.minute % 15 + local.second / 60) / 15
        return (
            self._slot(facility, local.weekday(), slot) * (1 - fraction)
            + self._slot(facility, local.weekday(), slot + 1) * fraction
        )

    def simulated_current(self, facility: FacilityId, at: datetime) -> float:
        local = at.astimezone(EASTERN)
        key = (facility, local.weekday(), local.hour * 4 + local.minute // 15)
        # Replay the most recent matching historical bucket as the simulated observation.
        return self.latest[key]


class DemoRepository:
    def __init__(self, path: Path = HISTORY_PATH):
        self.profile = HistoricalProfile(load_history(path))

    @staticmethod
    def anchor(now):
        utc = now.astimezone(timezone.utc)
        return utc.replace(second=0, microsecond=0, minute=utc.minute // 5 * 5)

    def occupancy(self, now):
        anchor = self.anchor(now)
        result = []
        for facility, capacity in CAPACITIES.items():
            count = round(self.profile.simulated_current(facility, anchor) * capacity / 100)
            result.append(
                Occupancy(
                    facility_id=facility,
                    facility_name=FACILITY_NAMES[facility],
                    occupancy=count,
                    remaining=capacity - count,
                    capacity=capacity,
                    occupancy_pct=100 * count / capacity,
                    observed_at=anchor,
                    source_updated_at=None,
                    provenance="demo",
                )
            )
        return result

    def forecast(self, now):
        anchor = self.anchor(now)
        result = []
        for observation in self.occupancy(now):
            facility = observation.facility_id
            residual = observation.occupancy_pct - self.profile.predict(facility, anchor)
            result.append(
                FacilityForecast(
                    facility_id=facility,
                    facility_name=FACILITY_NAMES[facility],
                    points=[
                        ForecastPoint(
                            forecast_time=anchor + timedelta(minutes=offset),
                            predicted_occupancy_pct=round(
                                max(
                                    0,
                                    min(
                                        100,
                                        self.profile.predict(
                                            facility, anchor + timedelta(minutes=offset)
                                        )
                                        + residual * math.exp(-offset / 90),
                                    ),
                                ),
                                2,
                            ),
                        )
                        for offset in range(0, 246, 5)
                    ],
                    generated_at=anchor,
                    observed_at=anchor,
                    confidence="low",
                    provenance="demo",
                )
            )
        return result

    def hours(self, now):
        # Explicit fictional hours keep the demo usable at any time of day.
        anchor = self.anchor(now)
        return {
            facility: [
                Interval(
                    start_time=anchor - timedelta(hours=1), end_time=anchor + timedelta(hours=5)
                )
            ]
            for facility in CAPACITIES
        }
