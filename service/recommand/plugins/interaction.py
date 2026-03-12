"""User interaction based recommendation plugin."""

from __future__ import annotations

from models.paper_recommand import PaperRecommandRequest
from service.recommand.plugins.base import RecommendationPlugin, clamp_score, limit_top_k
from service.recommand.repository import PaperRecommandRepository


class InteractionRecommendationPlugin(RecommendationPlugin):
    """Score papers from user interaction signals in ``activity`` table."""

    name = "interaction"

    def __init__(
        self,
        repository: PaperRecommandRepository,
        *,
        like_weight: float = 0.45,
        note_weight: float = 0.55,
        dislike_penalty: float = 0.4,
        recommended_penalty: float = 0.08,
    ) -> None:
        self.repository = repository
        self.like_weight = like_weight
        self.note_weight = note_weight
        self.dislike_penalty = dislike_penalty
        self.recommended_penalty = recommended_penalty

    def recommend(self, request: PaperRecommandRequest) -> dict[str, float]:
        activities = self.repository.list_activities()
        scores: dict[str, float] = {}

        for activity in activities:
            score = 0.0
            if activity.like > 0:
                score += self.like_weight
            elif activity.like < 0:
                score -= self.dislike_penalty

            if activity.user_notes.strip():
                score += self.note_weight

            score -= len(activity.recommendation_records) * self.recommended_penalty

            normalized = clamp_score(score)
            if normalized > 0:
                scores[activity.id] = normalized

        return limit_top_k(scores, request.top_k)
