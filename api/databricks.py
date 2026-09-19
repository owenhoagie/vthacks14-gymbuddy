"""Bounded SQL Statement Execution and typed GymBuddy warehouse access."""

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.clock import RealClock
from databricks.sdk.config import Config
from databricks.sdk.service.sql import Disposition, Format, StatementParameterListItem

from api.config import ROOT
from api.models import FACILITY_NAMES, FacilityForecast, FacilityId, IntegrationStatus, Occupancy


class WarehouseError(RuntimeError):
    """Safe to log: never includes SQL, credentials, or upstream error bodies."""


class BoundedRetryClock(RealClock):
    def sleep(self, seconds):
        # The SDK otherwise honors an arbitrarily long Retry-After beyond its deadline.
        super().sleep(min(seconds, 1))


@dataclass(frozen=True)
class DatabricksConfig:
    host: str = ""
    token: str = field(default="", repr=False)
    warehouse_id: str = ""
    catalog: str = ""
    schema: str = "gymbuddy"

    @classmethod
    def from_env(cls):
        from api.config import Settings

        return cls.from_settings(Settings())

    @classmethod
    def from_settings(cls, settings):
        return cls(
            settings.databricks_host,
            settings.databricks_token,
            settings.databricks_sql_warehouse_id,
            settings.databricks_catalog,
            settings.databricks_schema,
        )

    @property
    def configured(self):
        return all((self.host, self.token, self.warehouse_id, self.catalog, self.schema))

    def table(self, name):
        parts = (self.catalog, self.schema, name)
        if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", part) for part in parts):
            raise ValueError("Databricks catalog/schema/table must be simple SQL identifiers")
        return ".".join(f"`{part}`" for part in parts)


def timestamp(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    # SQL TIMESTAMP values without an offset are rendered in the UTC warehouse session.
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class DatabricksRepository:
    def __init__(
        self, config=None, client=None, timeout=180, sleep=time.sleep, clock=time.monotonic
    ):
        self.config = config or DatabricksConfig.from_env()
        self._client = client
        self.timeout, self.sleep, self.clock = timeout, sleep, clock
        self.connected = False

    @property
    def client(self):
        if not self.config.configured:
            raise WarehouseError("Databricks is not configured")
        if self._client is None:
            self._client = WorkspaceClient(
                config=Config(
                    host=self.config.host,
                    token=self.config.token,
                    auth_type="pat",
                    http_timeout_seconds=15,
                    retry_timeout_seconds=1,
                    clock=BoundedRetryClock(),
                )
            )
        return self._client

    def status(self):
        return IntegrationStatus(
            configured=self.config.configured,
            status=("ready" if self.connected else "unavailable")
            if self.config.configured
            else "not_configured",
        )

    def _call(self, function, deadline, **kwargs):
        for attempt in range(3):
            if self.clock() >= deadline:
                raise WarehouseError("Databricks operation timed out")
            try:
                return function(**kwargs)
            except WarehouseError:
                raise
            except Exception as exc:
                retryable = getattr(exc, "status_code", None) in (429, 500, 502, 503, 504)
                retryable |= type(exc).__name__ in (
                    "TooManyRequests",
                    "TemporarilyUnavailable",
                    "InternalError",
                    "DeadlineExceeded",
                    "TimeoutError",
                )
                if not retryable or attempt == 2:
                    raise WarehouseError("Databricks request failed") from None
                self.sleep(min(2**attempt, max(0, deadline - self.clock())))
        raise WarehouseError("Databricks request failed")

    def execute(self, sql, parameters=None):
        deadline = self.clock() + self.timeout
        statement_id = None
        try:
            api = self.client.statement_execution
            response = self._call(
                api.execute_statement,
                deadline,
                warehouse_id=self.config.warehouse_id,
                statement=sql,
                parameters=[
                    StatementParameterListItem(name=k, value=v)
                    for k, v in (parameters or {}).items()
                ],
                disposition=Disposition.INLINE,
                format=Format.JSON_ARRAY,
                wait_timeout="10s",
            )
            statement_id = response.statement_id
            while True:
                state = (
                    response.status.state.value if response.status and response.status.state else ""
                )
                if state == "SUCCEEDED":
                    break
                if state not in ("PENDING", "RUNNING") or not statement_id:
                    raise WarehouseError("Databricks statement failed")
                self.sleep(min(1, max(0, deadline - self.clock())))
                response = self._call(api.get_statement, deadline, statement_id=statement_id)
            if response.manifest and response.manifest.truncated:
                raise WarehouseError("Databricks result was truncated")
            columns = (
                [c.name for c in response.manifest.schema.columns]
                if (response.manifest and response.manifest.schema)
                else []
            )
            result, rows, seen = response.result, [], set()
            while result:
                rows.extend(dict(zip(columns, row)) for row in (result.data_array or []))
                next_index = result.next_chunk_index
                if next_index is None:
                    break
                if next_index in seen:
                    raise WarehouseError("Databricks returned repeated result chunks")
                seen.add(next_index)
                result = self._call(
                    api.get_statement_result_chunk_n,
                    deadline,
                    statement_id=statement_id,
                    chunk_index=next_index,
                )
            self.connected = True
            return rows
        except Exception:
            self.connected = False
            if statement_id and self.clock() >= deadline:
                try:
                    self.client.statement_execution.cancel_execution(statement_id)
                except Exception:
                    pass
            raise WarehouseError(
                "Databricks operation failed or timed out; safe to retry"
            ) from None

    def template(self, filename):
        self.config.table("raw_occupancy")  # validate identifiers before interpolation
        return (
            (ROOT / "databricks" / filename)
            .read_text()
            .replace("{{catalog}}", f"`{self.config.catalog}`")
            .replace("{{schema}}", f"`{self.config.schema}`")
        )

    def initialize(self):
        for filename in ("01_bronze.sql", "02_silver.sql"):
            sql = re.sub(r"--[^\n]*", "", self.template(filename))
            for statement in sql.split(";"):
                if statement.strip():
                    self.execute(statement)
        self.refresh_forecast()

    def merge(self, observations):
        if not observations:
            return
        # JSON is a named parameter, never interpolated SQL. Dedupe the MERGE source too.
        table = self.config.table("raw_occupancy")
        schema = (
            "facility_id STRING, facility_name STRING, source_facility_id STRING, "
            "occupancy BIGINT, remaining BIGINT, capacity BIGINT, occupancy_pct DOUBLE, "
            "observed_at STRING, source_updated_at STRING, source STRING"
        )
        sql = f"""MERGE INTO {table} target USING (
          SELECT * EXCEPT (rn) FROM (
            SELECT *, ROW_NUMBER() OVER (PARTITION BY facility_id, observed_at
              ORDER BY facility_id) rn FROM (
              SELECT r.* EXCEPT (observed_at, source_updated_at),
                CAST(r.observed_at AS TIMESTAMP) observed_at,
                CAST(r.source_updated_at AS TIMESTAMP) source_updated_at,
                CURRENT_TIMESTAMP() ingested_at
              FROM (SELECT EXPLODE(FROM_JSON(:rows, 'ARRAY<STRUCT<{schema}>>')) r)
            )
          ) WHERE rn = 1
        ) source ON target.facility_id = source.facility_id
          AND target.observed_at = source.observed_at
        WHEN NOT MATCHED THEN INSERT *"""
        self.execute(sql, {"rows": json.dumps(observations)})

    def refresh_forecast(self):
        self.execute(self.template("03_gold.sql"))

    def get_occupancy(self):
        rows = self.execute(f"""SELECT * EXCEPT (rn, observed_at, source_updated_at),
          DATE_FORMAT(observed_at, 'yyyy-MM-dd HH:mm:ss.SSSSSSXXX') observed_at,
          DATE_FORMAT(source_updated_at, 'yyyy-MM-dd HH:mm:ss.SSSSSSXXX') source_updated_at
          FROM (
          SELECT *, ROW_NUMBER() OVER (PARTITION BY facility_id ORDER BY observed_at DESC) rn
          FROM {self.config.table("raw_occupancy")}) WHERE rn = 1""")
        return [
            Occupancy(
                facility_id=r["facility_id"],
                facility_name=FACILITY_NAMES[FacilityId(r["facility_id"])],
                occupancy=int(r["occupancy"]),
                remaining=int(r["remaining"]),
                capacity=int(r["capacity"]),
                occupancy_pct=float(r["occupancy_pct"]),
                observed_at=timestamp(r["observed_at"]),
                source_updated_at=timestamp(r["source_updated_at"])
                if r["source_updated_at"]
                else None,
                provenance="live",
            )
            for r in rows
        ]

    def get_forecast(self, start=None, end=None, facility_id=None):
        rows = self.execute(
            "SELECT * EXCEPT (forecast_time, observed_at, generated_at), "
            "DATE_FORMAT(forecast_time, 'yyyy-MM-dd HH:mm:ss.SSSSSSXXX') forecast_time, "
            "DATE_FORMAT(observed_at, 'yyyy-MM-dd HH:mm:ss.SSSSSSXXX') observed_at, "
            "DATE_FORMAT(generated_at, 'yyyy-MM-dd HH:mm:ss.SSSSSSXXX') generated_at "
            f"FROM {self.config.table('occupancy_forecast')} "
            "ORDER BY facility_id, forecast_time"
        )
        grouped = {}
        for r in rows:
            fid = FacilityId(r["facility_id"])
            if facility_id and fid != facility_id:
                continue
            point_time = timestamp(r["forecast_time"])
            if (start and point_time < start) or (end and point_time > end):
                continue
            if fid not in grouped:
                grouped[fid] = dict(
                    facility_id=fid,
                    facility_name=FACILITY_NAMES[fid],
                    points=[],
                    observed_at=timestamp(r["observed_at"]),
                    generated_at=timestamp(r["generated_at"]),
                    confidence=r["confidence"],
                    provenance="live",
                )
            grouped[fid]["points"].append(
                dict(
                    forecast_time=point_time,
                    predicted_occupancy_pct=float(r["predicted_occupancy_pct"]),
                )
            )
        return [FacilityForecast(**value) for value in grouped.values()]

    def backfill_observations(self, csv_path):
        from collector.sync import synchronize

        return synchronize(Path(csv_path), self, full=True)
