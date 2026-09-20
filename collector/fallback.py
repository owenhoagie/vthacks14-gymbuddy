"""Publish real collector history and a low-confidence warehouse-free forecast."""

import csv
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from api.models import FACILITY_NAMES, FacilityForecast, ForecastPoint, Occupancy
from api.storage import atomic_json
from collector.sync import validate_row


def publish(outbox: Path, history: Path, destination: Path):
    now = datetime.now(timezone.utc)
    unique = {}
    for path in (history, outbox):
        if not path.exists():
            continue
        with path.open(newline="") as stream:
            for raw in csv.DictReader(stream):
                try:
                    row = validate_row(raw)
                    observed = datetime.fromisoformat(row["observed_at"])
                    if now - observed <= timedelta(hours=48):
                        unique[(row["facility_id"], row["observed_at"])] = row
                except (ValueError, KeyError, TypeError, ZeroDivisionError):
                    logging.warning("Skipping invalid fallback history row")
    rows = sorted(unique.values(), key=lambda row: row["observed_at"])
    occupancy, forecasts = [], []
    for facility, name in FACILITY_NAMES.items():
        records = [row for row in rows if row["facility_id"] == facility]
        if not records:
            continue
        latest = records[-1]
        observed = datetime.fromisoformat(latest["observed_at"])
        window = [
            row
            for row in records
            if datetime.fromisoformat(row["observed_at"]) >= observed - timedelta(minutes=30)
        ]
        mean = sum(row["occupancy_pct"] for row in window) / len(window)
        minutes = (observed - datetime.fromisoformat(window[0]["observed_at"])).total_seconds() / 60
        slope = (
            max(-0.25, min(0.25, (latest["occupancy_pct"] - window[0]["occupancy_pct"]) / minutes))
            if len(window) >= 3 and minutes > 0
            else 0
        )
        if len(window) < 3:
            mean = latest["occupancy_pct"]
        occupancy.append(
            Occupancy(
                facility_id=facility,
                facility_name=name,
                occupancy=latest["occupancy"],
                remaining=latest["remaining"],
                capacity=latest["capacity"],
                occupancy_pct=latest["occupancy_pct"],
                observed_at=observed,
                source_updated_at=latest["source_updated_at"],
                provenance="cached",
            ).model_dump(mode="json")
        )
        forecasts.append(
            FacilityForecast(
                facility_id=facility,
                facility_name=name,
                observed_at=observed,
                generated_at=now,
                confidence="low",
                provenance="cached",
                forecast_source="collector_fallback",
                points=[
                    ForecastPoint(
                        forecast_time=observed + timedelta(minutes=m),
                        predicted_occupancy_pct=round(max(0, min(100, mean + slope * m)), 4),
                    )
                    for m in range(0, 241, 5)
                ],
            ).model_dump(mode="json")
        )
    if not occupancy:
        raise ValueError("No real observations available for fallback")
    history.parent.mkdir(parents=True, exist_ok=True)
    from collector.run import FIELDS

    temporary = history.with_suffix(".tmp")
    with temporary.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(history)
    atomic_json(destination, {"occupancy": occupancy, "forecast": forecasts})
    logging.info("Published real fallback snapshot with %s observations", len(rows))
