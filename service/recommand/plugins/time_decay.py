"""Time-based recommendation plugin."""

from __future__ import annotations

from datetime import timedelta

from models.paper_recommand import PaperRecommandRequest
from service.recommand.plugins.base import RecommendationPlugin, clamp_score, limit_top_k
from service.recommand.repository import PaperRecommandRepository


class TimeDecayRecommendationPlugin(RecommendationPlugin):
    """Recommend newer papers based on ``fetched_at`` freshness."""

    name = "time"

    def __init__(self, repository: PaperRecommandRepository, *, freshness_window_days: int = 30) -> None:
        self.repository = repository
        self.freshness_window_days = freshness_window_days

    def recommend(self, request: PaperRecommandRequest) -> dict[str, float]:
        if self.freshness_window_days <= 0:
            return {}

        now = request.resolved_now()
        window_start = now - timedelta(days=self.freshness_window_days)
        papers = self.repository.list_papers(fetched_from=window_start)

        scores: dict[str, float] = {}
        for paper in papers:
            age_seconds = (now - paper.fetched_at).total_seconds()
            age_days = max(age_seconds, 0.0) / 86400.0
            if age_days >= self.freshness_window_days:
                continue

            score = 1.0 - (age_days / float(self.freshness_window_days))
            normalized = clamp_score(score)
            if normalized > 0:
                scores[paper.id] = normalized

        return limit_top_k(scores, request.top_k)
