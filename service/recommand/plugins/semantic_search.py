"""Semantic recommendation plugin using embedding search."""

from __future__ import annotations

from typing import Callable

from models.paper_recommand import PaperRecommandRequest
from service.embedding.embedding_service import PaperEmbeddingService
from service.recommand.plugins.base import RecommendationPlugin, clamp_score, limit_top_k


class SemanticSearchRecommendationPlugin(RecommendationPlugin):
    """Generate recommendations from semantic retrieval results."""

    name = "semantic"

    def __init__(
        self,
        *,
        default_top_k: int = 20,
        embedding_service: PaperEmbeddingService | None = None,
        embedding_service_factory: Callable[[], PaperEmbeddingService] | None = None,
    ) -> None:
        self.default_top_k = default_top_k
        self._embedding_service = embedding_service
        self._embedding_service_factory = embedding_service_factory

    def recommend(self, request: PaperRecommandRequest) -> dict[str, float]:
        query = request.query.strip()
        if not query:
            return {}

        top_k = request.top_k if request.top_k > 0 else self.default_top_k
        service = self._get_embedding_service()
        hits = service.search(query, top_k=top_k)

        scores: dict[str, float] = {}
        for hit in hits:
            # sqlite-vec cosine distance is lower-is-better, convert to 0..1 score.
            score = 1.0 / (1.0 + max(float(hit.distance), 0.0))
            scores[hit.paper.id] = clamp_score(score)

        return limit_top_k(scores, top_k)

    def _get_embedding_service(self) -> PaperEmbeddingService:
        if self._embedding_service is not None:
            return self._embedding_service
        if self._embedding_service_factory is None:
            raise RuntimeError("Semantic plugin missing embedding service factory")
        self._embedding_service = self._embedding_service_factory()
        return self._embedding_service
