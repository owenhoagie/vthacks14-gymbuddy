"""Shared live snapshots: network work happens only in background refresh workers."""

import hashlib
import logging
import threading
from datetime import timedelta

import httpx
from pydantic import BaseModel, Field, model_validator

from api.databricks import DatabricksConfig, DatabricksRepository
from api.hours import get_hours
from api.models import FACILITY_NAMES, FacilityForecast, Occupancy
from api.repository import LocalRepository, utc_now
from api.storage import atomic_json

log = logging.getLogger(__name__)


class Snapshot(BaseModel):
    occupancy: list[Occupancy] = Field(default_factory=list)
    forecast: list[FacilityForecast] = Field(default_factory=list)

    @model_validator(mode="after")
    def real_only(self):
        for records in (self.occupancy, self.forecast):
            if len({r.facility_id for r in records}) != len(records):
                raise ValueError("Duplicate snapshot facilities")
            for record in records:
                if record.provenance not in ("live", "cached") or record.observed_at is None:
                    raise ValueError("Snapshot must contain real observations")
                if record.observed_at > utc_now() + timedelta(minutes=5):
                    raise ValueError("Future snapshot observation")
        return self


class LiveRepository:
    def __init__(self, settings, warehouse=None, hours_loader=get_hours):
        self.settings = settings
        self.warehouse = warehouse or DatabricksRepository(DatabricksConfig.from_settings(settings))
        if settings.api_runtime == "serverless":
            self.warehouse.timeout = 20
        self.local = LocalRepository(settings)
        self.hours_loader = hours_loader
        config = self.warehouse.config
        identity = f"{config.host}/{config.warehouse_id}/{config.catalog}/{config.schema}"
        identity += "/" + settings.live_data_source
        suffix = hashlib.sha256(identity.encode()).hexdigest()[:12]
        self.cache_path = settings.occupancy_csv_path.with_name(f"live-snapshot.{suffix}.json")
        self.snapshot = Snapshot()
        self.last_success = None
        self.connected = False
        self.open_hours = {f: [] for f in FACILITY_NAMES}
        self.hours_until = None
        self.lock = threading.Lock()
        self.refresh_lock = threading.Lock()
        self.last_attempt = None
        self.stop_event = threading.Event()
        self.threads = []
        try:
            self.snapshot = Snapshot.model_validate_json(self.cache_path.read_text())
        except (OSError, ValueError):
            pass

    def start(self):
        if self.settings.api_runtime == "serverless":
            return
        for function, name in ((self.refresh, "warehouse"), (self.refresh_hours, "hours")):
            thread = threading.Thread(
                target=self._loop, args=(function,), name=f"live-{name}", daemon=True
            )
            self.threads.append(thread)
            thread.start()

    def prepare_request(self, include_hours=False):
        if self.settings.api_runtime != "serverless":
            return
        # Serverless instances can freeze between requests: never rely on daemon threads.
        with self.refresh_lock:
            now = utc_now()
            if self.last_attempt is None or now - self.last_attempt >= timedelta(seconds=60):
                self.last_attempt = now
                self.refresh()
            if include_hours:
                self.refresh_hours()

    def stop(self):
        self.stop_event.set()
        for thread in self.threads:
            thread.join(timeout=2)

    def _loop(self, function):
        while not self.stop_event.is_set():
            function()
            self.stop_event.wait(60)

    def refresh(self):
        try:
            if self.settings.live_data_source == "collector_fallback":
                response = httpx.get(
                    self.settings.live_fallback_url,
                    params={"minute": int(utc_now().timestamp() // 60)},
                    headers={"Cache-Control": "no-cache"},
                    timeout=8,
                )
                response.raise_for_status()
                if len(response.content) > 1_000_000:
                    raise ValueError("Fallback snapshot too large")
                snapshot = Snapshot.model_validate_json(response.content)
                if (
                    not snapshot.occupancy
                    or not snapshot.forecast
                    or any(row.forecast_source != "collector_fallback" for row in snapshot.forecast)
                ):
                    raise ValueError("Invalid collector fallback snapshot")
            else:
                snapshot = Snapshot(
                    occupancy=self.warehouse.get_occupancy(), forecast=self.warehouse.get_forecast()
                )
            # Disk failures must not discard a successful warehouse read.
            try:
                atomic_json(self.cache_path, snapshot.model_dump(mode="json"))
            except OSError:
                log.warning("Could not persist live recovery snapshot")
            with self.lock:
                self.snapshot = snapshot
                self.last_success = utc_now()
                self.connected = True
        except Exception as exc:
            with self.lock:
                self.connected = False
            log.warning(
                "Live warehouse refresh unavailable (%s); retaining snapshot", type(exc).__name__
            )

    def refresh_hours(self):
        now = utc_now()
        with self.lock:
            if self.hours_until and now < self.hours_until - timedelta(minutes=1):
                return
        try:
            # Extra 15 minutes keeps the rolling four-hour request horizon covered until refresh.
            hours = self.hours_loader(now, now + timedelta(hours=4, minutes=15))
            with self.lock:
                self.open_hours = hours
                self.hours_until = now + timedelta(minutes=15)
        except Exception as exc:
            log.warning(
                "Hours refresh failed (%s); expired hours remain unavailable", type(exc).__name__
            )

    def _live(self, now):
        return bool(
            self.connected
            and self.last_success
            and now - self.last_success <= timedelta(seconds=120)
        )

    def _stale(self, observed, now):
        return observed is None or now - observed > timedelta(
            minutes=self.settings.stale_after_minutes
        )

    def occupancy(self, now):
        with self.lock:
            live = self._live(now)
            current = {
                r.facility_id: r.model_copy(
                    update={
                        "provenance": "live"
                        if live and self.settings.live_data_source == "databricks"
                        else "cached",
                        "stale": self._stale(r.observed_at, now),
                    }
                )
                for r in self.snapshot.occupancy
            }
        if not live:
            for row in self.local.occupancy(now):
                previous = current.get(row.facility_id)
                if row.observed_at and (not previous or row.observed_at > previous.observed_at):
                    current[row.facility_id] = row
        return [
            current.get(f, Occupancy(facility_id=f, facility_name=name, provenance="unavailable"))
            for f, name in FACILITY_NAMES.items()
        ]

    def forecast(self, now):
        with self.lock:
            live = self._live(now)
            current = {
                r.facility_id: r.model_copy(
                    update={
                        "provenance": "live"
                        if live and self.settings.live_data_source == "databricks"
                        else "cached",
                        "stale": self._stale(r.observed_at, now),
                    }
                )
                for r in self.snapshot.forecast
            }
        return [
            current.get(
                f,
                FacilityForecast(
                    facility_id=f,
                    facility_name=name,
                    points=[],
                    generated_at=None,
                    observed_at=None,
                    confidence="low",
                    provenance="unavailable",
                ),
            )
            for f, name in FACILITY_NAMES.items()
        ]

    def hours(self, now):
        with self.lock:
            if not self.hours_until or now >= self.hours_until:
                return {f: [] for f in FACILITY_NAMES}
            return {f: list(intervals) for f, intervals in self.open_hours.items()}

    def status(self, now):
        from api.models import IntegrationStatus

        return IntegrationStatus(
            configured=self.settings.databricks_configured,
            status=(
                "ready"
                if self._live(now) and self.settings.live_data_source == "databricks"
                else "unavailable"
            )
            if self.settings.databricks_configured
            else "not_configured",
        )

    def ready(self, now):
        return (
            self._live(now)
            and all(r.observed_at and not r.stale for r in self.occupancy(now))
            and all(r.points and not r.stale for r in self.forecast(now))
        )
