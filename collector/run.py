"""Fetch VT's public HTML and durably append successful observations.

Run `python -m collector --once` or `python -m collector` from the repo root.
The standard-library-only collector can start before backend dependencies install.
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import re
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

URL = "https://connect.recsports.vt.edu/FacilityOccupancy/GetFacilityData"
DISPLAY_TYPE = "00000000-0000-0000-0000-000000004490"
FACILITIES = {
    "mccomas": ("McComas Hall", "232d714e-5b3e-4b0d-9936-e6a738150ec4"),
    "war_memorial": ("War Memorial Hall", "55069633-b56e-43b7-a68a-64d79364988d"),
}
FIELDS = [
    "facility_id",
    "facility_name",
    "source_facility_id",
    "occupancy",
    "remaining",
    "capacity",
    "occupancy_pct",
    "observed_at",
    "source_updated_at",
    "source",
]
DEFAULT_PATH = Path(__file__).resolve().parents[1] / "data" / "occupancy_raw.csv"
log = logging.getLogger(__name__)


class OccupancyHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.canvases: list[dict[str, str]] = []
        self.labels: dict[str, str] = {}
        self.label_id: str | None = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "canvas" and "data-occupancy" in attrs:
            self.canvases.append(attrs)
        if tag == "span" and str(attrs.get("id", "")).startswith("chartDesc-"):
            self.label_id = attrs["id"]
            self.labels[self.label_id] = ""

    def handle_data(self, data):
        if self.label_id:
            self.labels[self.label_id] += data

    def handle_endtag(self, tag):
        if tag == "span":
            self.label_id = None


def parse_occupancy(html: str, facility_id: str, observed_at: datetime) -> dict:
    if observed_at.utcoffset() is None:
        raise ValueError("observed_at must include a timezone")
    name, source_id = FACILITIES[facility_id]
    parser = OccupancyHTML()
    parser.feed(html)
    candidates = [
        c
        for c in parser.canvases
        if c.get("id", "").removesuffix("-sm") == f"occupancyChart-{source_id}"
    ]
    if not candidates:
        raise ValueError(f"No occupancy canvas for {facility_id}")
    # A repeated responsive canvas describes the same observation, never another row.
    readings = set()
    for canvas in candidates:
        count = int(canvas["data-occupancy"])
        remaining = int(canvas["data-remaining"])
        capacity = count + remaining
        # VT can clamp remaining to zero during overcapacity. Preserve its labeled limit.
        label = parser.labels.get(canvas.get("aria-labelledby", ""), "")
        match = re.search(r"Max Occupancy:\s*([\d,]+)", label, re.IGNORECASE)
        if match:
            capacity = int(match.group(1).replace(",", ""))
        if count < 0 or capacity <= 0:
            raise ValueError(f"Invalid occupancy for {facility_id}")
        readings.add((count, remaining, capacity))
    if len(readings) != 1:
        raise ValueError(f"Conflicting responsive occupancy canvases for {facility_id}")
    count, remaining, capacity = readings.pop()
    return {
        "facility_id": facility_id,
        "facility_name": name,
        "source_facility_id": source_id,
        "occupancy": count,
        "remaining": remaining,
        "capacity": capacity,
        "occupancy_pct": round(100 * count / capacity, 2),
        "observed_at": observed_at.astimezone(timezone.utc).isoformat(),
        "source_updated_at": None,
        "source": "vt_recsports",
    }


def fetch_html(facility_id: str) -> str:
    request = Request(
        URL,
        data=urlencode(
            {"facilityId": FACILITIES[facility_id][1], "occupancyDisplayType": DISPLAY_TYPE}
        ).encode(),
        headers={"User-Agent": "GymBuddy/0.1 (VTHacks occupancy collector)"},
    )
    with urlopen(request, timeout=25) as response:
        return response.read().decode("utf-8")


def append_observation(path: Path, observation: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # O_APPEND plus an advisory lock protects the header and row from another collector.
    import fcntl

    with path.open("a", newline="") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        handle.seek(0, os.SEEK_END)
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        if handle.tell() == 0:
            writer.writeheader()
        writer.writerow(observation)
        handle.flush()
        os.fsync(handle.fileno())


def collect_once(path: Path = DEFAULT_PATH, fetcher=fetch_html) -> tuple[int, int]:
    successes = failures = 0
    for facility_id in FACILITIES:
        try:
            html = fetcher(facility_id)
            row = parse_occupancy(html, facility_id, datetime.now(timezone.utc))
            append_observation(path, row)
            successes += 1
            log.info(
                "Saved %s: %s/%s (fetched %s)",
                facility_id,
                row["occupancy"],
                row["capacity"],
                row["observed_at"],
            )
        except Exception:
            failures += 1
            log.exception("Collection failed for %s; existing observations retained", facility_id)
    return successes, failures


def latest_observations(path: Path = DEFAULT_PATH) -> dict[str, dict]:
    """Read the append-only cache, preserving the original observation timestamp."""
    latest = {}
    if not path.exists():
        return latest
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                facility = row["facility_id"]
                if facility not in FACILITIES:
                    continue
                observed_at = datetime.fromisoformat(row["observed_at"])
                if observed_at.utcoffset() is None:
                    continue
                row["occupancy"] = int(row["occupancy"])
                row["capacity"] = int(row["capacity"])
                row["remaining"] = (
                    int(row["remaining"])
                    if "remaining" in row
                    else row["capacity"] - row["occupancy"]
                )
                row["occupancy_pct"] = float(row["occupancy_pct"])
                row["source_updated_at"] = row["source_updated_at"] or None
                if facility not in latest or observed_at > datetime.fromisoformat(
                    latest[facility]["observed_at"]
                ):
                    latest[facility] = row
            except (KeyError, TypeError, ValueError):
                log.warning("Skipping malformed cached observation")
    return latest


def main() -> int:
    # Optional .env loading once the project dependencies have been installed.
    try:
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    except ImportError:
        pass
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Collect both gyms once, then exit")
    parser.add_argument(
        "--interval", type=float, default=float(os.getenv("COLLECTOR_INTERVAL_SECONDS", "300"))
    )
    parser.add_argument(
        "--output", type=Path, default=Path(os.getenv("OCCUPANCY_CSV_PATH", str(DEFAULT_PATH)))
    )
    args = parser.parse_args()
    if args.interval <= 0:
        parser.error("--interval must be positive")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    worker = None
    if os.getenv("DATABRICKS_TOKEN"):
        from collector.sync import UploadWorker

        worker = UploadWorker(args.output)
        if not args.once:
            worker.start()
    try:
        while True:
            started = time.monotonic()
            _, failures = collect_once(args.output)
            if args.once:
                if worker:
                    from collector.sync import synchronize

                    try:
                        synchronize(args.output, worker.warehouse)
                    except Exception as exc:
                        log.warning("Upload failed (%s); CSV retained", type(exc).__name__)
                        return 1
                return 1 if failures else 0
            time.sleep(max(0, args.interval - (time.monotonic() - started)))
    except KeyboardInterrupt:
        log.info("Collector stopped; saved observations retained")
        return 0
    finally:
        if worker and not args.once:
            worker.stop()


if __name__ == "__main__":
    raise SystemExit(main())
