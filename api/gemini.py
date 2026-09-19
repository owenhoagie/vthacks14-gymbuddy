"""Bounded Gemini tool calling over authoritative, already-ranked workout options.

Calendar blocks never leave the scheduler. Gemini cannot alter candidates, ranking,
confidence, provenance, warnings, or timestamps. Only its explanation is generated.
"""

import hashlib
import json
import logging
import re
from functools import lru_cache
from threading import Lock
from time import monotonic
from typing import Literal

from google import genai
from google.genai import types
from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.models import IntegrationStatus, RecommendationRequest, RecommendationResponse

logger = logging.getLogger(__name__)
FALLBACK_WARNING = "Gemini is temporarily unavailable; your workout uses schedule-based ranking."
SYSTEM = """You are GymBuddy's concise workout planning assistant.
First call get_workout_options. Then call explain_workout with the primary and
alternative IDs exactly as returned. The tool has already checked the entire
workout against availability, opening hours, forecast freshness, and crowd ranking.
Do not change its ranking. Explain the practical tradeoff in one or two short,
friendly sentences grounded ONLY in the tool output. Do not invent calendar events,
equipment, travel times, crowd causes, future certainty, or other gym information.
Your explanation must be qualitative: do not repeat numbers, percentages, dates,
or clock times (these are rendered separately from authoritative data). Do not
include links or markup. A demo is synthetic and must never be described as real
observations. Low confidence is uncertainty, not a guarantee. Never describe an
above-tolerance option as meeting tolerance. No actions are taken or bookings made.
"""


class Explanation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    primary_id: Literal["primary"]
    alternative_id: Literal["alternative", "none"]
    explanation: str = Field(min_length=20, max_length=600)

    @field_validator("explanation")
    @classmethod
    def qualitative_text(cls, text: str) -> str:
        text = text.strip()
        if len(text) < 20 or re.search(r"\d|%|https?://|[<>]", text):
            raise ValueError("Explanation must be qualitative plain text")
        return text


def _function(name: str, description: str, parameters: dict) -> types.FunctionDeclaration:
    return types.FunctionDeclaration(
        name=name, description=description, parameters_json_schema=parameters
    )


READ_TOOL = _function(
    "get_workout_options",
    "Read the validated best workout and alternative with ranking context.",
    {"type": "object", "properties": {}, "additionalProperties": False},
)
WRITE_TOOL = _function(
    "explain_workout",
    "Explain the supplied primary workout without changing its selection.",
    Explanation.model_json_schema(),
)


def _config(tool: types.FunctionDeclaration) -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        system_instruction=SYSTEM,
        tools=[types.Tool(function_declarations=[tool])],
        tool_config=types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(
                mode="ANY",
                allowed_function_names=[tool.name],
            )
        ),
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        max_output_tokens=1024,
        temperature=0.2,
    )


def _call(response, name: str):
    # Reject blocked, truncated, empty, parallel, or unexpected calls.
    if not response.candidates or len(response.candidates) != 1:
        raise ValueError("Missing candidate")
    if response.candidates[0].finish_reason != types.FinishReason.STOP:
        raise ValueError("Incomplete model response")
    calls = response.function_calls or []
    if len(calls) != 1 or calls[0].name != name:
        raise ValueError("Unexpected function call")
    return calls[0]


class GeminiService:
    def __init__(
        self, key: str, model: str, timeout: float = 12, *, client_factory=None, clock=monotonic
    ):
        self.key, self.model, self.timeout = key, model, timeout
        self.client_factory = client_factory or genai.Client
        self.clock = clock
        self.gate = Lock()
        self.last_success: float | None = None
        self.retry_after = 0.0
        # Per-instance, bounded, short-lived cache. Contains no calendar blocks.
        self.cache: dict[str, tuple[float, str]] = {}

    @property
    def configured(self):
        return bool(self.key and self.model)

    def status(self) -> IntegrationStatus:
        recent = self.last_success is not None and self.clock() - self.last_success < 900
        return IntegrationStatus(
            configured=self.configured,
            status=("ready" if recent and self.clock() >= self.retry_after else "unavailable")
            if self.configured
            else "not_configured",
        )

    def explain(self, request: RecommendationRequest, result: RecommendationResponse):
        if not self.configured or result.status != "ok" or result.recommendation is None:
            return result
        fallback = result.model_copy(update={"warnings": [*result.warnings, FALLBACK_WARNING]})
        # Drop the request's private calendar blocks and search bounds entirely.
        context = {
            "primary": {"id": "primary", **result.recommendation.model_dump(mode="json")},
            "alternative": {"id": "alternative", **result.alternative.model_dump(mode="json")}
            if result.alternative
            else None,
            "alternative_id": "alternative" if result.alternative else "none",
            "workout_duration_minutes": request.workout_duration_minutes,
            "preferred_gyms": [gym.value for gym in request.preferred_gyms],
            "crowd_tolerance": request.crowd_tolerance,
            "data_mode": result.data_mode,
            "ranking_explanation": result.explanation,
            "warnings": result.warnings,
        }
        cache_key = hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()
        # Do not queue requests behind a slow upstream or spend quota during a cooldown.
        if not self.gate.acquire(blocking=False):
            return fallback
        try:
            now = self.clock()
            self.cache = {key: entry for key, entry in self.cache.items() if entry[0] > now}
            if cache_key in self.cache:
                return result.model_copy(
                    update={"method": "gemini", "explanation": self.cache[cache_key][1]}
                )
            if now < self.retry_after:
                return fallback
            with self.client_factory(
                api_key=self.key,
                http_options=types.HttpOptions(
                    timeout=int(self.timeout * 1000),
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            ) as client:
                contents = [
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_text(
                                text="Read my validated workout options and explain the best window.",
                            )
                        ],
                    )
                ]
                first = client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=_config(READ_TOOL),
                )
                read_call = _call(first, "get_workout_options")
                if read_call.args not in (None, {}):
                    raise ValueError("Read tool takes no arguments")
                # Preserve the model content, including thought signatures, for the next turn.
                contents = [
                    *contents,
                    first.candidates[0].content,
                    types.Content(
                        role="user",
                        parts=[
                            types.Part(
                                function_response=types.FunctionResponse(
                                    name=read_call.name,
                                    id=read_call.id,
                                    response=context,
                                )
                            )
                        ],
                    ),
                ]
                second = client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=_config(WRITE_TOOL),
                )
                explanation = Explanation.model_validate(_call(second, "explain_workout").args)
                if explanation.alternative_id != context["alternative_id"]:
                    raise ValueError("Invalid alternative selection")
            self.last_success = self.clock()
            self.retry_after = 0
            if len(self.cache) >= 64:
                self.cache.pop(next(iter(self.cache)))
            self.cache[cache_key] = (self.clock() + 300, explanation.explanation)
            return result.model_copy(
                update={"method": "gemini", "explanation": explanation.explanation}
            )
        except Exception as exc:
            # Do not log exception messages, credentials, prompts, or calendar contents.
            logger.warning("Gemini fallback: %s", type(exc).__name__)
            self.last_success = None
            self.retry_after = self.clock() + 60
            return fallback
        finally:
            self.gate.release()


@lru_cache(maxsize=4)
def get_gemini_service(key: str, model: str, timeout: float = 12) -> GeminiService:
    return GeminiService(key, model, timeout)
