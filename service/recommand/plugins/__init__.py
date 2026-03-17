"""Built-in recommendation plugins."""

from service.recommand.plugins.base import RecommendationPlugin
from service.recommand.plugins.interaction import InteractionRecommendationPlugin
from service.recommand.plugins.institution import InstitutionRecommendationPlugin
from service.recommand.plugins.semantic_search import SemanticSearchRecommendationPlugin
from service.recommand.plugins.time_decay import TimeDecayRecommendationPlugin

__all__ = [
    "RecommendationPlugin",
    "SemanticSearchRecommendationPlugin",
    "InteractionRecommendationPlugin",
    "TimeDecayRecommendationPlugin",
    "InstitutionRecommendationPlugin",
]
