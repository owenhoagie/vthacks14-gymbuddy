"""GymBuddy HTTP API. Run with uvicorn api.main:app --reload."""

import logging
from typing import Annotated

from fastapi import Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime
from starlette.exceptions import HTTPException

from api.config import Settings, get_settings
from api.models import (
    ErrorResponse,
    FacilityId,
    ForecastResponse,
    HealthResponse,
    IntegrationStatus,
    OccupancyResponse,
    RecommendationRequest,
    RecommendationResponse,
)
from api.recommendation import recommend
from api.repository import Repository, get_repository, utc_now

logger = logging.getLogger(__name__)
app = FastAPI(
    title="GymBuddy API",
    version="0.1.0",
    responses={422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[s.strip() for s in get_settings().cors_origins.split(",") if s.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


def error_response(status: int, code: str, message: str, details=None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details}},
    )


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError):
    # Input values and arbitrary validator contexts can contain secrets or fail JSON encoding.
    details = [
        {"location": list(error["loc"]), "message": error["msg"], "type": error["type"]}
        for error in exc.errors()
    ]
    return error_response(422, "validation_error", "The request is invalid.", details)


@app.exception_handler(HTTPException)
async def http_error(_request: Request, exc: HTTPException):
    return error_response(exc.status_code, "http_error", str(exc.detail))


@app.exception_handler(Exception)
async def unexpected_error(_request: Request, exc: Exception):
    logger.error("Unexpected API failure: %s", type(exc).__name__)
    return error_response(500, "internal_error", "An unexpected server error occurred.")


SettingsDependency = Annotated[Settings, Depends(get_settings)]
RepositoryDependency = Annotated[Repository, Depends(get_repository)]


@app.get("/health", response_model=HealthResponse)
def health(settings: SettingsDependency):
    return HealthResponse(
        status="ok" if settings.data_mode == "demo" else "degraded",
        data_mode=settings.data_mode,
        integrations={
            "databricks": IntegrationStatus(
                configured=settings.databricks_configured,
                status="not_implemented" if settings.databricks_configured else "not_configured",
            ),
            "gemini": IntegrationStatus(
                configured=settings.gemini_configured,
                status="not_implemented" if settings.gemini_configured else "not_configured",
            ),
        },
    )


@app.get("/occupancy", response_model=OccupancyResponse)
def occupancy(repository: RepositoryDependency, settings: SettingsDependency):
    return OccupancyResponse(
        facilities=repository.occupancy(utc_now()), data_mode=settings.data_mode
    )


@app.get("/forecast", response_model=ForecastResponse)
def forecast(
    repository: RepositoryDependency,
    settings: SettingsDependency,
    facility_id: FacilityId | None = None,
    start_time: Annotated[AwareDatetime | None, Query()] = None,
    end_time: Annotated[AwareDatetime | None, Query()] = None,
):
    if start_time and end_time and end_time <= start_time:
        return error_response(422, "validation_error", "end_time must be later than start_time.")
    facilities = repository.forecast(utc_now())
    if facility_id:
        facilities = [f for f in facilities if f.facility_id == facility_id]
    if start_time or end_time:
        facilities = [
            f.model_copy(
                update={
                    "points": [
                        p
                        for p in f.points
                        if (start_time is None or p.forecast_time >= start_time)
                        and (end_time is None or p.forecast_time <= end_time)
                    ]
                }
            )
            for f in facilities
        ]
    return ForecastResponse(facilities=facilities, data_mode=settings.data_mode)


@app.post("/recommend", response_model=RecommendationResponse)
def recommendation(
    request: RecommendationRequest, repository: RepositoryDependency, settings: SettingsDependency
):
    now = utc_now()
    return recommend(
        request, repository.forecast(now), repository.hours(now), now, settings.data_mode
    )
