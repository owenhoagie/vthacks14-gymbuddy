"""Frozen public contracts; frontend types are generated from these models."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="after", check_fields=False)
    @classmethod
    def normalize_utc(cls, value: Any) -> Any:
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc)
        return value


class FacilityId(str, Enum):
    mccomas = "mccomas"
    war_memorial = "war_memorial"


FACILITY_NAMES = {
    FacilityId.mccomas: "McComas Hall",
    FacilityId.war_memorial: "War Memorial Hall",
}

Provenance = Literal["demo", "live", "cached", "unavailable"]
Confidence = Literal["low", "medium", "high"]


class Interval(Contract):
    start_time: AwareDatetime
    end_time: AwareDatetime

    @model_validator(mode="after")
    def ordered(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be later than start_time")
        return self


class Occupancy(Contract):
    opening_status: Literal["open", "closed", "unknown"] = "unknown"
    opens_at: AwareDatetime | None = None
    closes_at: AwareDatetime | None = None
    facility_id: FacilityId
    facility_name: str
    occupancy: int | None = Field(default=None, ge=0)
    remaining: int | None = None
    capacity: int | None = Field(default=None, gt=0)
    occupancy_pct: float | None = Field(default=None, ge=0)
    observed_at: AwareDatetime | None = None
    source_updated_at: AwareDatetime | None = None
    provenance: Provenance
    stale: bool = False


class OccupancyResponse(Contract):
    facilities: list[Occupancy]
    data_mode: Literal["demo", "live"]


class ForecastPoint(Contract):
    forecast_time: AwareDatetime
    predicted_occupancy_pct: float = Field(ge=0, le=100)


class FacilityForecast(Contract):
    forecast_source: Literal["databricks", "collector_fallback"] | None = None
    facility_id: FacilityId
    facility_name: str
    points: list[ForecastPoint]
    generated_at: AwareDatetime | None
    observed_at: AwareDatetime | None
    confidence: Confidence
    provenance: Provenance
    stale: bool = False


class ForecastResponse(Contract):
    facilities: list[FacilityForecast]
    data_mode: Literal["demo", "live"]


class RecommendationRequest(Interval):
    unavailable: list[Interval] = Field(default_factory=list, max_length=50)
    workout_duration_minutes: int = Field(default=75, ge=15, le=180)
    preferred_gyms: list[FacilityId] = Field(default_factory=list, max_length=2)
    crowd_tolerance: Literal["low", "medium", "high"] = "low"

    @model_validator(mode="after")
    def bounded_horizon(self):
        if (self.end_time - self.start_time).total_seconds() > 4 * 3600:
            raise ValueError("Search horizon must not exceed four hours")
        return self


class Candidate(Interval):
    facility_id: FacilityId
    facility_name: str
    predicted_occupancy_pct: float = Field(ge=0, le=100)
    confidence: Confidence
    provenance: Provenance
    exceeds_tolerance: bool = False


class RecommendationResponse(Contract):
    status: Literal["ok", "no_available_window", "data_unavailable"]
    recommendation: Candidate | None = None
    alternative: Candidate | None = None
    explanation: str
    method: Literal["deterministic", "gemini"] = "deterministic"
    warnings: list[str] = Field(default_factory=list)
    generated_at: AwareDatetime
    data_mode: Literal["demo", "live"]


class IntegrationStatus(Contract):
    configured: bool
    status: Literal["not_configured", "not_implemented", "ready", "unavailable"]


class HealthResponse(Contract):
    status: Literal["ok", "degraded"]
    data_mode: Literal["demo", "live"]
    integrations: dict[str, IntegrationStatus]


class ErrorDetail(Contract):
    code: str
    message: str
    details: Any = None


class ErrorResponse(Contract):
    error: ErrorDetail
