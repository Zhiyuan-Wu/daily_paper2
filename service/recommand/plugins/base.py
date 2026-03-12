"""Plugin protocol for recommendation algorithms."""

from __future__ import annotations

from abc import ABC, abstractmethod

from models.paper_recommand import PaperRecommandRequest


class RecommendationPlugin(ABC):
    """Base class for recommendation plugins."""

    name: str

    @abstractmethod
    def recommend(self, request: PaperRecommandRequest) -> dict[str, float]:
        """Return paper_id -> score mapping (score in [0, 1])."""


def clamp_score(value: float) -> float:
    if value <= 0:
        return 0.0
    if value >= 1:
        return 1.0
    return float(value)


def limit_top_k(scores: dict[str, float], top_k: int) -> dict[str, float]:
    if top_k <= 0:
        return {}
    if len(scores) <= top_k:
        return scores
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:top_k]
    return dict(ordered)
