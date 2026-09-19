"""Run the API and collector together on a single persistent server.

One supervisor, one API process, and one collector share a durable data directory.
If either process dies, terminate the other and let the hosting provider restart us.
"""

import logging
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path

from api.config import ROOT, Settings

log = logging.getLogger(__name__)


def commands(port):
    if not 1 <= int(port) <= 65535:
        raise ValueError("PORT must be between 1 and 65535")
    return [
        [
            sys.executable,
            "-m",
            "uvicorn",
            "api.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            str(port),
            "--workers",
            "1",
        ],
        [sys.executable, "-m", "collector"],
    ]


def stop_children(children):
    for child in children:
        if child.poll() is None:
            child.terminate()
    for child in children:
        try:
            child.wait(timeout=15)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings()
    if settings.data_mode != "live" or not settings.databricks_configured:
        log.error("Hosted server requires DATA_MODE=live and configured Databricks credentials")
        return 1
    directory = settings.occupancy_csv_path.parent
    directory.mkdir(parents=True, exist_ok=True)
    # Fail startup if the persistent outbox is not writable.
    probe = directory / ".write-check"
    probe.touch()
    probe.unlink()
    children = []
    stopping = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stopping.set())
    try:
        for command in commands(os.getenv("PORT", "8000")):
            children.append(subprocess.Popen(command, cwd=ROOT))
        log.info("Hosted API and collector started; observations persist in %s", Path(directory))
        while not stopping.wait(1):
            if any(child.poll() is not None for child in children):
                log.error("A hosted process exited; stopping both for provider restart")
                return 1
        return 0
    finally:
        stop_children(children)


if __name__ == "__main__":
    raise SystemExit(main())
