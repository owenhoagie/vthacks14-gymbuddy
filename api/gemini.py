"""Integration seam: Gemini function calling is a subsequent milestone.

Future implementations must select validated deterministic candidates only.
No configured key triggers a model request in the credential-free baseplate.
"""

from api.models import RecommendationResponse


class GeminiService:
    def explain(self, deterministic: RecommendationResponse) -> RecommendationResponse:
        return deterministic
