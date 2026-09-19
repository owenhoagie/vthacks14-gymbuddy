from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from google.genai import types

from api.config import Settings, get_settings
from api.demo import DemoRepository
from api.gemini import FALLBACK_WARNING, GeminiService
from api.main import app
from api.models import RecommendationRequest
from api.recommendation import recommend
from api.repository import get_repository

NOW = datetime(2026, 9, 19, 14, tzinfo=timezone.utc)


def response(name, args, finish=types.FinishReason.STOP):
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                finish_reason=finish,
                content=types.Content(
                    role="model", parts=[types.Part.from_function_call(name=name, args=args)]
                ),
            )
        ]
    )


class FakeClient:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []
        self.options = None
        self.models = self
        self.closed = False

    def factory(self, **options):
        self.options = options
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.closed = True

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        item = self.outputs.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def scenario():
    repository = DemoRepository()
    request = RecommendationRequest(
        start_time=NOW,
        end_time=NOW + timedelta(hours=4),
        unavailable=[{"start_time": NOW, "end_time": NOW + timedelta(minutes=15)}],
        workout_duration_minutes=75,
        preferred_gyms=["mccomas"],
    )
    result = recommend(request, repository.forecast(NOW), repository.hours(NOW), NOW)
    assert result.recommendation and result.alternative
    return request, result


def valid_outputs():
    return [
        response("get_workout_options", {}),
        response(
            "explain_workout",
            {
                "primary_id": "primary",
                "alternative_id": "alternative",
                "explanation": "This synthetic forecast suggests a quieter workout that fits your schedule. Treat the crowd estimate as a guide, not a guarantee.",
            },
        ),
    ]


def test_real_tool_round_trip_preserves_candidates_and_private_calendar(scenario):
    request, result = scenario
    fake = FakeClient(valid_outputs())
    service = GeminiService("test-secret", "test-model", client_factory=fake.factory)
    assert service.status().status == "unavailable"
    output = service.explain(request, result)
    assert output.method == "gemini"
    for field in (
        "recommendation",
        "alternative",
        "warnings",
        "generated_at",
        "data_mode",
        "status",
    ):
        assert getattr(output, field) == getattr(result, field)
    assert result.method == "deterministic"  # no mutation
    assert len(fake.calls) == 2 and fake.closed
    first, second = fake.calls
    assert first["config"].automatic_function_calling.disable
    assert second["contents"][1] == valid_outputs()[0].candidates[0].content
    context = second["contents"][2].parts[0].function_response.response
    assert second["contents"][2].role == "user"
    assert "unavailable" not in context and "start_time" not in context
    assert context["primary"]["matches_gym_preference"] == (
        result.recommendation.facility_id in request.preferred_gyms
    )
    assert context["alternative"]["matches_gym_preference"] == (
        result.alternative.facility_id in request.preferred_gyms
    )
    assert (
        context["primary"]["start_time"]
        == result.recommendation.model_dump(mode="json")["start_time"]
    )
    assert "test-secret" not in str(fake.calls)
    assert fake.options["http_options"].retry_options.attempts == 1
    assert fake.options["http_options"].timeout == 12000
    assert service.status().status == "ready"
    assert (
        service.explain(request, result) == output
    )  # repeated requests reuse validated explanation
    assert len(fake.calls) == 2


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {
            "primary_id": "invented",
            "alternative_id": "alternative",
            "explanation": "A valid length explanation.",
        },
        {
            "primary_id": "primary",
            "alternative_id": "none",
            "explanation": "A valid length explanation.",
        },
        {
            "primary_id": "primary",
            "alternative_id": "alternative",
            "explanation": "Occupancy will be 5% tomorrow.",
        },
        {"primary_id": "primary", "alternative_id": "alternative", "explanation": "x" * 601},
        {
            "primary_id": "primary",
            "alternative_id": "alternative",
            "explanation": "A valid length explanation.",
            "start_time": "invented",
        },
        {
            "primary_id": "primary",
            "alternative_id": "alternative",
            "explanation": "Visit https://example.com for your workout.",
        },
    ],
)
def test_malformed_selection_falls_back_without_changing_result(scenario, bad):
    request, result = scenario
    fake = FakeClient([response("get_workout_options", {}), response("explain_workout", bad)])
    service = GeminiService("key", "model", client_factory=fake.factory)
    output = service.explain(request, result)
    assert output == result.model_copy(update={"warnings": [*result.warnings, FALLBACK_WARNING]})
    assert service.status().status == "unavailable"
    assert fake.closed


@pytest.mark.parametrize(
    "failure",
    [
        httpx.ReadTimeout("secret upstream details"),
        RuntimeError("429 quota exhausted: secret"),
        types.GenerateContentResponse(),
        response("get_workout_options", {}, types.FinishReason.MAX_TOKENS),
        response("delete_database", {}),
        response("get_workout_options", {"calendar": "private"}),
    ],
)
def test_failure_cooldown_and_sanitized_logs(scenario, failure, caplog):
    request, result = scenario
    fake = FakeClient([failure, *valid_outputs()])
    clock = [100.0]
    service = GeminiService("secret", "model", client_factory=fake.factory, clock=lambda: clock[0])
    assert service.explain(request, result).method == "deterministic"
    assert service.explain(request, result).method == "deterministic"
    assert len(fake.calls) == 1
    assert "secret" not in caplog.text and "quota" not in caplog.text
    clock[0] += 61
    assert service.explain(request, result).method == "gemini"
    assert len(fake.calls) == 3
    clock[0] += 901
    assert service.status().status == "unavailable"


def test_no_model_calls_for_missing_key_no_window_or_stale_forecast(scenario):
    request, result = scenario
    fake = FakeClient([])
    service = GeminiService("", "model", client_factory=fake.factory)
    assert service.explain(request, result) == result
    assert service.status().status == "not_configured"
    configured = GeminiService("key", "model", client_factory=fake.factory)
    for status in ("no_available_window", "data_unavailable"):
        empty = result.model_copy(update={"status": status, "recommendation": None})
        assert configured.explain(request, empty) == empty
    assert not fake.calls


def test_busy_instance_does_not_queue_or_consume_quota(scenario):
    fake = FakeClient([])
    service = GeminiService("key", "model", client_factory=fake.factory)
    with service.gate:
        assert service.explain(*scenario).method == "deterministic"
    assert not fake.calls


def test_cache_expiry_preference_changes_and_second_call_timeout(scenario):
    request, result = scenario
    clock = [100.0]
    fake = FakeClient([*valid_outputs(), *valid_outputs(), *valid_outputs()])
    service = GeminiService("key", "model", client_factory=fake.factory, clock=lambda: clock[0])
    assert service.explain(request, result).method == "gemini"
    changed = request.model_copy(update={"crowd_tolerance": "high"})
    assert service.explain(changed, result).method == "gemini"
    assert len(fake.calls) == 4
    clock[0] += 301
    assert service.explain(request, result).method == "gemini"
    assert len(fake.calls) == 6
    fake = FakeClient([valid_outputs()[0], httpx.ReadTimeout("private upstream error")])
    service = GeminiService("key", "model", client_factory=fake.factory)
    output = service.explain(request, result)
    assert output.method == "deterministic" and output.explanation == result.explanation
    assert len(fake.calls) == 2 and fake.closed


def test_null_alternative_and_multiple_calls(scenario):
    request, result = scenario
    result = result.model_copy(update={"alternative": None})
    outputs = valid_outputs()
    outputs[1].candidates[0].content.parts[0].function_call.args["alternative_id"] = "none"
    fake = FakeClient(outputs)
    assert (
        GeminiService("key", "model", client_factory=fake.factory).explain(request, result).method
        == "gemini"
    )
    multiple = valid_outputs()[0]
    multiple.candidates[0].content.parts.append(
        types.Part.from_function_call(name="get_workout_options", args={})
    )
    fake = FakeClient([multiple])
    assert (
        GeminiService("key", "model", client_factory=fake.factory).explain(request, result).method
        == "deterministic"
    )


def test_api_wires_service_and_health(monkeypatch, scenario):
    request, _ = scenario
    fake = FakeClient(valid_outputs())
    service = GeminiService("key", "model", client_factory=fake.factory)
    monkeypatch.setattr("api.main.get_gemini_service", lambda *args: service)
    monkeypatch.setattr("api.main.utc_now", lambda: NOW)
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, data_mode="demo")
    app.dependency_overrides[get_repository] = DemoRepository
    try:
        with TestClient(app) as client:
            assert client.get("/health").json()["integrations"]["gemini"]["status"] == "unavailable"
            output = client.post("/recommend", json=request.model_dump(mode="json"))
            assert output.status_code == 200 and output.json()["method"] == "gemini"
            assert client.get("/health").json()["integrations"]["gemini"]["status"] == "ready"
    finally:
        app.dependency_overrides.clear()
