"""Idempotent CSV outbox upload. Collection and warehouse work run independently."""

import csv
import fcntl
import hashlib
import json
import logging
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from api.databricks import DatabricksRepository, WarehouseError
from api.models import Occupancy
from api.storage import atomic_json
from collector.run import FACILITIES, FIELDS

log = logging.getLogger(__name__)


def state_path(path, warehouse):
    config = warehouse.config
    target = f"{config.host}/{config.warehouse_id}/{config.catalog}/{config.schema}"
    key = hashlib.sha256(target.encode()).hexdigest()[:12]
    return path.with_name(f"{path.stem}.{key}.checkpoint.json")


@contextmanager
def sync_lock(path, warehouse):
    checkpoint = state_path(path, warehouse)
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    with checkpoint.with_suffix(".lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield checkpoint


def validate_row(row):
    observed = datetime.fromisoformat(row["observed_at"].replace("Z", "+00:00"))
    source_time = row["source_updated_at"] or None
    item = Occupancy(
        facility_id=row["facility_id"],
        facility_name=row["facility_name"],
        occupancy=row["occupancy"],
        remaining=row["remaining"],
        capacity=row["capacity"],
        occupancy_pct=row["occupancy_pct"],
        observed_at=observed,
        source_updated_at=source_time,
        provenance="live",
    )
    if observed > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise ValueError("Future observation")
    name, source_id = FACILITIES[item.facility_id]
    if row["source_facility_id"] != source_id or row["source"] != "vt_recsports":
        raise ValueError("Unknown observation source")
    if any(
        value is None or not -(2**63) <= value < 2**63
        for value in (item.occupancy, item.remaining, item.capacity)
    ):
        raise ValueError("Observation counts must fit warehouse BIGINT columns")
    value = {key: row[key] for key in FIELDS}
    value.update(
        facility_name=name,
        occupancy=item.occupancy,
        remaining=item.remaining,
        capacity=item.capacity,
        occupancy_pct=round(100 * item.occupancy / item.capacity, 2),
        observed_at=item.observed_at.isoformat(),
        source_updated_at=item.source_updated_at.isoformat() if item.source_updated_at else None,
    )
    return value


def synchronize(path: Path, warehouse: DatabricksRepository, full=False, batch_size=100):
    if not warehouse.config.configured:
        raise WarehouseError("Databricks is not configured")
    with sync_lock(path, warehouse) as checkpoint:
        # Take a stable CSV snapshot without blocking collection during any network work.
        with path.open(newline="") as source:
            fcntl.flock(source, fcntl.LOCK_SH)
            rows = list(csv.DictReader(source))
        try:
            state = json.loads(checkpoint.read_text())
        except (OSError, ValueError):
            state = {}
        if not isinstance(state, dict):
            state = {}
        done = state.get("rows", 0)
        if not isinstance(done, int) or done < 0:
            done = 0

        def digest(count):
            return hashlib.sha256(json.dumps(rows[:count]).encode()).hexdigest()

        if full or done > len(rows) or state.get("digest") != digest(done):
            done = 0
        merged = rejected = 0
        # Mark refresh pending BEFORE MERGE: crash/uncertain completion cannot lose refresh work.
        for offset in range(done, len(rows), batch_size):
            batch = []
            for line, row in enumerate(rows[offset : offset + batch_size], start=offset + 2):
                try:
                    batch.append(validate_row(row))
                except (ValueError, KeyError, TypeError, ZeroDivisionError):
                    rejected += 1
                    log.warning("Rejected invalid CSV observation at line %s", line)
            state = dict(rows=offset, digest=digest(offset), refresh_pending=True)
            atomic_json(checkpoint, state)
            warehouse.merge(batch)
            done = min(offset + batch_size, len(rows))
            state.update(rows=done, digest=digest(done))
            atomic_json(checkpoint, state)
            merged += len(batch)
        if state.get("refresh_pending") or full:
            warehouse.refresh_forecast()
            state["refresh_pending"] = False
            atomic_json(checkpoint, state)
        return dict(processed=merged, rejected=rejected, checkpoint_rows=done)


class UploadWorker:
    def __init__(self, path, warehouse=None, interval=60):
        self.path = path
        self.warehouse = warehouse or DatabricksRepository()
        self.interval = interval
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.run, name="databricks-upload", daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=2)

    def run(self):
        while not self.stop_event.is_set():
            try:
                result = synchronize(self.path, self.warehouse)
                if result["processed"]:
                    log.info("Databricks synchronized %s observations", result["processed"])
            except Exception as exc:
                log.warning(
                    "Databricks sync unavailable (%s); CSV retained for retry", type(exc).__name__
                )
            self.stop_event.wait(self.interval)
