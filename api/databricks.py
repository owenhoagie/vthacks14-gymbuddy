"""Databricks repository boundary for the next integration milestone.

Credentials alone do not activate an unverified implementation. The runnable
baseplate uses the fixture repository or locally collected occupancy instead.
"""

import re
from dataclasses import dataclass, field

from api.models import IntegrationStatus


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

        settings = Settings()
        return cls(
            host=settings.databricks_host,
            token=settings.databricks_token,
            warehouse_id=settings.databricks_sql_warehouse_id,
            catalog=settings.databricks_catalog,
            schema=settings.databricks_schema,
        )

    @property
    def configured(self) -> bool:
        return all((self.host, self.token, self.warehouse_id, self.catalog, self.schema))

    def table(self, name: str) -> str:
        parts = (self.catalog, self.schema, name)
        if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", part) for part in parts):
            raise ValueError("Databricks catalog/schema/table must be simple SQL identifiers")
        return ".".join(f"`{part}`" for part in parts)


class DatabricksRepository:
    def __init__(self, config: DatabricksConfig | None = None):
        self.config = config or DatabricksConfig.from_env()

    def status(self) -> IntegrationStatus:
        return IntegrationStatus(
            configured=self.config.configured,
            status="not_implemented" if self.config.configured else "not_configured",
        )

    def get_occupancy(self):
        raise NotImplementedError(
            "Connect SQL Statement Execution API and verify Bronze/Silver reads before enabling Databricks"
        )

    def backfill_observations(self, csv_path):
        """Future idempotent MERGE keyed by (facility_id, observed_at); retain CSV."""
        raise NotImplementedError(
            "Implement validated, bounded CSV MERGE batches and checkpoint only confirmed SQL success"
        )

    def get_forecast(self, start, end, facility_id=None):
        raise NotImplementedError(
            "Connect SQL Statement Execution API and verify Gold forecasts before enabling Databricks"
        )
