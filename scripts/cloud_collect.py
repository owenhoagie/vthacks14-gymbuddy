"""One scheduled collection, preserving only unconfirmed observations for retry."""

import csv
import logging
import os
import tempfile
from pathlib import Path

from api.databricks import DatabricksRepository
from collector.run import FIELDS, collect_once
from collector.sync import synchronize


def clear_confirmed(path):
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w", newline="") as stream:
            csv.DictWriter(stream, fieldnames=FIELDS).writeheader()
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def run(path, warehouse=None, fetcher=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        clear_confirmed(path)
    _, failures = collect_once(path, **({"fetcher": fetcher} if fetcher else {}))
    try:
        result = synchronize(path, warehouse or DatabricksRepository())
        if result["rejected"]:
            # Preserve malformed rows for diagnosis; never silently discard them.
            return 1
        clear_confirmed(path)
        logging.info("Uploaded observations and refreshed Gold; retry outbox is empty")
    except Exception as exc:
        logging.error("Upload failed (%s); outbox retained for next run", type(exc).__name__)
        return 1
    return 1 if failures else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(run(Path(os.getenv("OCCUPANCY_CSV_PATH", "data/occupancy_raw.csv"))))
