"""Reproducible fake history and held-out evaluation. No warehouse credentials or writes."""

import csv
import json
import math
import random
from datetime import datetime, timedelta, timezone
from statistics import mean

from api.config import ROOT
from api.demo import CAPACITIES, EASTERN, HISTORY_PATH, HistoricalProfile, load_history

SEED = 140926
START = datetime(2026, 7, 13, tzinfo=EASTERN)
DAYS = 63


def generate(path=HISTORY_PATH):
    rng = random.Random(SEED)
    with path.open("w", newline="") as target:
        writer = csv.writer(target)
        writer.writerow(
            ["facility_id", "observed_at", "occupancy", "capacity", "occupancy_pct", "provenance"]
        )
        for day in range(DAYS):
            at = START + timedelta(days=day)
            weekend = at.weekday() >= 5
            for index, (facility, capacity) in enumerate(CAPACITIES.items()):
                day_effect, drift = rng.gauss(0, 3), 0.0
                for slot in range(96):
                    hour = slot / 4

                    def bump(center, width, height):
                        return height * math.exp(-0.5 * ((hour - center) / width) ** 2)

                    if weekend:
                        expected = 5 + bump(11.5 + index, 1.6, 45) + bump(16.5 - index, 1.7, 53)
                    else:
                        expected = 5 + bump(7.5 + index / 2, 1.1, 24) + bump(12.5, 1.5, 29)
                        expected += bump(17.5 + index, 1.7, 72 - index * 8)
                    # Smooth disturbances prevent the model from seeing identical template days.
                    drift = drift * 0.8 + rng.gauss(0, 1.3)
                    pct = max(0, min(98, expected + day_effect + drift + rng.gauss(0, 1)))
                    count = round(pct * capacity / 100)
                    observed = (at + timedelta(minutes=slot * 15)).astimezone(timezone.utc)
                    writer.writerow(
                        [
                            facility.value,
                            observed.isoformat(),
                            count,
                            capacity,
                            round(100 * count / capacity, 4),
                            "synthetic",
                        ]
                    )


def evaluate(rows):
    cutoff = START + timedelta(days=56)
    train = [row for row in rows if row["at"] < cutoff]
    holdout = [row for row in rows if row["at"] >= cutoff]
    profile = HistoricalProfile(train)
    metrics = {}
    for facility in CAPACITIES:
        held = [r for r in holdout if r["facility_id"] == facility]
        average = mean(r["pct"] for r in train if r["facility_id"] == facility)
        metrics[facility.value] = {
            "seasonal_mae_percentage_points": round(
                mean(abs(profile.predict(facility, r["at"]) - r["pct"]) for r in held), 3
            ),
            "constant_mean_mae_percentage_points": round(
                mean(abs(average - r["pct"]) for r in held), 3
            ),
        }
    return {
        "synthetic": True,
        "seed": SEED,
        "rows": len(rows),
        "history_days": DAYS,
        "interval_minutes": 15,
        "training_days": 56,
        "holdout_days": 7,
        "start": START.isoformat(),
        "end_exclusive": (START + timedelta(days=DAYS)).isoformat(),
        "method": "Eastern weekday and quarter-hour means, adjacent-slot smoothing",
        "serving": "Refit all 63 days; simulated current residual decays over 90 minutes",
        "metrics": metrics,
        "caveat": "Evaluation uses fabricated data only. It is not evidence of real-world forecasting accuracy. Demo opening hours are fictional.",
    }


def main():
    generate()
    report = evaluate(load_history())
    (ROOT / "fixtures" / "demo.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
