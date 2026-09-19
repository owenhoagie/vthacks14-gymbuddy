"""Server-only configuration. No secret values are returned through the API."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    data_mode: Literal["demo", "live"] = "demo"
    api_runtime: Literal["persistent", "serverless"] = "persistent"
    gemini_api_key: str = ""
    gemini_model: str = ""
    gemini_timeout_seconds: float = Field(default=12, ge=1, le=20)
    databricks_host: str = ""
    databricks_token: str = ""
    databricks_sql_warehouse_id: str = ""
    databricks_catalog: str = ""
    databricks_schema: str = "gymbuddy"
    cors_origins: str = "http://localhost:3000"
    occupancy_csv_path: Path = ROOT / "data" / "occupancy_raw.csv"
    stale_after_minutes: int = Field(default=15, ge=1)

    @property
    def databricks_configured(self) -> bool:
        return all(
            (
                self.databricks_host,
                self.databricks_token,
                self.databricks_sql_warehouse_id,
                self.databricks_catalog,
                self.databricks_schema,
            )
        )

    @property
    def gemini_configured(self) -> bool:
        return bool(self.gemini_api_key and self.gemini_model)


@lru_cache
def get_settings() -> Settings:
    return Settings()
