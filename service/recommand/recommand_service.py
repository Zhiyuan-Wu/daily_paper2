"""Plugin-based paper recommendation service."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any, Iterable

from models.paper_recommand import PaperRecommandRequest, PaperRecommendation
from service.embedding.embedding_service import PaperEmbeddingService
from service.recommand.config import get_paper_recommand_config
from service.recommand.plugins import (
    InteractionRecommendationPlugin,
    InstitutionRecommendationPlugin,
    RecommendationPlugin,
    SemanticSearchRecommendationPlugin,
    TimeDecayRecommendationPlugin,
)
from service.recommand.plugins.base import clamp_score
from service.recommand.repository import PaperRecommandRepository


class PaperRecommandService:
    """Entry-point for paper recommendation with pluggable algorithms."""

    def __init__(
        self,
        db_path: str | Path | None = None,
        paper_table: str | None = None,
        activity_table: str | None = None,
        extend_metadata_table: str | None = None,
        default_algorithm: str | None = None,
        default_top_k: int | None = None,
        config_path: str | Path | None = None,
        semantic_embedding_service: PaperEmbeddingService | None = None,
    ) -> None:
        cfg = get_paper_recommand_config(config_path)
        plugin_cfg = _as_mapping(cfg.get("plugins"), "paper_recommand.plugins")
        semantic_cfg = _as_mapping(plugin_cfg.get("semantic"), "paper_recommand.plugins.semantic")
        interaction_cfg = _as_mapping(
            plugin_cfg.get("interaction"), "paper_recommand.plugins.interaction"
        )
        time_cfg = _as_mapping(plugin_cfg.get("time"), "paper_recommand.plugins.time")
        institution_cfg = _as_mapping(
            plugin_cfg.get("institution")
            or {
                "enabled": True,
                "freshness_window_days": 30,
                "normalization_cap": 8.0,
                "weight": 1.0,
            },
            "paper_recommand.plugins.institution",
        )

        self.db_path = Path(db_path or _as_str(cfg.get("db_path"), "paper_recommand.db_path"))
        self.paper_table = paper_table or _as_str(
            cfg.get("paper_table") or "papers", "paper_recommand.paper_table"
        )
        self.activity_table = activity_table or _as_str(
            cfg.get("activity_table") or "activity", "paper_recommand.activity_table"
        )
        self.extend_metadata_table = extend_metadata_table or _as_str(
            cfg.get("extend_metadata_table") or "extend_metadata",
            "paper_recommand.extend_metadata_table",
        )

        self.default_algorithm = (default_algorithm or cfg.get("default_algorithm") or "fusion").lower()
        self.default_top_k = (
            default_top_k
            if default_top_k is not None
            else _as_int(cfg.get("default_top_k") or 20, "paper_recommand.default_top_k")
        )

        self.repo = PaperRecommandRepository(
            self.db_path,
            paper_table=self.paper_table,
            activity_table=self.activity_table,
            extend_metadata_table=self.extend_metadata_table,
        )
        self.plugins: dict[str, RecommendationPlugin] = {}
        self.fusion_weights: dict[str, float] = {}

        if _as_bool(semantic_cfg.get("enabled"), "paper_recommand.plugins.semantic.enabled"):
            semantic_top_k = _as_int(
                semantic_cfg.get("top_k") or self.default_top_k,
                "paper_recommand.plugins.semantic.top_k",
            )
            self.register_plugin(
                SemanticSearchRecommendationPlugin(
                    default_top_k=semantic_top_k,
                    embedding_service=semantic_embedding_service,
                    embedding_service_factory=(
                        lambda: PaperEmbeddingService(db_path=self.db_path, config_path=config_path)
                    ),
                ),
                fusion_weight=_as_float(
                    semantic_cfg.get("weight", 1.0),
                    "paper_recommand.plugins.semantic.weight",
                ),
            )

        if _as_bool(
            interaction_cfg.get("enabled"), "paper_recommand.plugins.interaction.enabled"
        ):
            self.register_plugin(
                InteractionRecommendationPlugin(
                    self.repo,
                    like_weight=_as_float(
                        interaction_cfg.get("like_weight") or 0.45,
                        "paper_recommand.plugins.interaction.like_weight",
                    ),
                    note_weight=_as_float(
                        interaction_cfg.get("note_weight") or 0.55,
                        "paper_recommand.plugins.interaction.note_weight",
                    ),
                    dislike_penalty=_as_float(
                        interaction_cfg.get("dislike_penalty") or 0.4,
                        "paper_recommand.plugins.interaction.dislike_penalty",
                    ),
                    recommended_penalty=_as_float(
                        interaction_cfg.get("recommended_penalty") or 0.08,
                        "paper_recommand.plugins.interaction.recommended_penalty",
                    ),
                ),
                fusion_weight=_as_float(
                    interaction_cfg.get("weight", 1.0),
                    "paper_recommand.plugins.interaction.weight",
                ),
            )

        if _as_bool(time_cfg.get("enabled"), "paper_recommand.plugins.time.enabled"):
            self.register_plugin(
                TimeDecayRecommendationPlugin(
                    self.repo,
                    freshness_window_days=_as_int(
                        time_cfg.get("freshness_window_days") or 30,
                        "paper_recommand.plugins.time.freshness_window_days",
                    ),
                ),
                fusion_weight=_as_float(
                    time_cfg.get("weight", 1.0),
                    "paper_recommand.plugins.time.weight",
                ),
            )

        if _as_bool(
            institution_cfg.get("enabled"), "paper_recommand.plugins.institution.enabled"
        ):
            self.register_plugin(
                InstitutionRecommendationPlugin(
                    self.repo,
                    freshness_window_days=_as_int(
                        institution_cfg.get("freshness_window_days") or 30,
                        "paper_recommand.plugins.institution.freshness_window_days",
                    ),
                    normalization_cap=_as_float(
                        institution_cfg.get("normalization_cap") or 8.0,
                        "paper_recommand.plugins.institution.normalization_cap",
                    ),
                ),
                fusion_weight=_as_float(
                    institution_cfg.get("weight", 1.0),
                    "paper_recommand.plugins.institution.weight",
                ),
            )

    def register_plugin(self, plugin: RecommendationPlugin, *, fusion_weight: float = 1.0) -> None:
        name = plugin.name.lower()
        self.plugins[name] = plugin
        self.fusion_weights[name] = fusion_weight

    def unregister_plugin(self, algorithm: str) -> None:
        name = algorithm.lower()
        self.plugins.pop(name, None)
        self.fusion_weights.pop(name, None)

    def list_algorithms(self) -> list[str]:
        return ["fusion", *sorted(self.plugins.keys())]

    def recommend(
        self,
        *,
        algorithm: str | None = None,
        query: str | None = None,
        top_k: int | None = None,
        now: datetime | date | str | None = None,
        plugin_payload: dict[str, Any] | None = None,
    ) -> list[PaperRecommendation]:
        """Return ranked paper recommendations with full metadata."""
        resolved_algorithm = (algorithm or self.default_algorithm or "fusion").lower()
        resolved_top_k = top_k if top_k is not None else self.default_top_k
        if resolved_top_k <= 0:
            return []

        request = PaperRecommandRequest(
            query=(query or "").strip(),
            top_k=resolved_top_k,
            now=_as_datetime(now),
            plugin_payload=plugin_payload or {},
        )

        if resolved_algorithm == "fusion":
            return self._recommend_fusion(request)

        plugin = self.plugins.get(resolved_algorithm)
        if plugin is None:
            raise ValueError(
                f"Unknown recommendation algorithm: {resolved_algorithm}. "
                f"Available: {', '.join(self.list_algorithms())}"
            )

        scores = _normalize_score_map(plugin.recommend(request))
        return self._materialize_results(
            final_scores=scores,
            component_scores={paper_id: {plugin.name: score} for paper_id, score in scores.items()},
            include_fusion_key=False,
            top_k=resolved_top_k,
        )

    def _recommend_fusion(self, request: PaperRecommandRequest) -> list[PaperRecommendation]:
        if not self.plugins:
            return []

        per_algorithm_scores: dict[str, dict[str, float]] = {}
        for name, plugin in self.plugins.items():
            try:
                per_algorithm_scores[name] = _normalize_score_map(plugin.recommend(request))
            except Exception:  # noqa: BLE001
                # Fusion should stay available even if one plugin is temporarily unavailable.
                per_algorithm_scores[name] = {}

        paper_ids: set[str] = set()
        for score_map in per_algorithm_scores.values():
            paper_ids.update(score_map.keys())
        if not paper_ids:
            return []

        normalized_weights = _normalize_fusion_weights(self.fusion_weights, self.plugins.keys())
        final_scores: dict[str, float] = {}
        component_scores: dict[str, dict[str, float]] = {}
        for paper_id in paper_ids:
            per_plugin = {
                name: per_algorithm_scores[name].get(paper_id, 0.0)
                for name in sorted(self.plugins.keys())
            }
            fused = clamp_score(
                sum(per_plugin[name] * normalized_weights.get(name, 0.0) for name in per_plugin)
            )
            if fused <= 0:
                continue
            final_scores[paper_id] = fused
            component_scores[paper_id] = per_plugin

        return self._materialize_results(
            final_scores=final_scores,
            component_scores=component_scores,
            include_fusion_key=True,
            top_k=request.top_k,
        )

    def _materialize_results(
        self,
        *,
        final_scores: dict[str, float],
        component_scores: dict[str, dict[str, float]],
        include_fusion_key: bool,
        top_k: int,
    ) -> list[PaperRecommendation]:
        if not final_scores:
            return []

        ordered_ids = [
            paper_id
            for paper_id, _ in sorted(final_scores.items(), key=lambda item: (-item[1], item[0]))
        ][:top_k]

        paper_map = self.repo.get_papers_by_ids(ordered_ids)

        results: list[PaperRecommendation] = []
        for paper_id in ordered_ids:
            paper = paper_map.get(paper_id)
            if paper is None:
                continue

            algo_scores = dict(component_scores.get(paper_id, {}))
            if include_fusion_key:
                algo_scores["fusion"] = final_scores[paper_id]

            results.append(
                PaperRecommendation(
                    paper=paper,
                    score=final_scores[paper_id],
                    algorithm_scores=algo_scores,
                )
            )
        return results

def _normalize_score_map(raw: dict[str, float]) -> dict[str, float]:
    normalized: dict[str, float] = {}
    for paper_id, score in raw.items():
        if not isinstance(paper_id, str) or not paper_id.strip():
            continue
        if not isinstance(score, (float, int)):
            continue
        value = clamp_score(float(score))
        if value > 0:
            normalized[paper_id] = value
    return normalized


def _as_datetime(value: datetime | date | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=timezone.utc)

    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)

    if len(value) == 10:
        return datetime.combine(parsed.date(), time.min, tzinfo=timezone.utc)
    return parsed


def _as_mapping(value: Any, key_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Config '{key_name}' must be a mapping")
    return value


def _as_str(value: Any, key_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Config '{key_name}' must be a non-empty string")
    return value


def _as_int(value: Any, key_name: str) -> int:
    if not isinstance(value, int):
        raise ValueError(f"Config '{key_name}' must be an integer")
    return value


def _as_float(value: Any, key_name: str) -> float:
    if isinstance(value, (float, int)):
        return float(value)
    raise ValueError(f"Config '{key_name}' must be a number")


def _as_bool(value: Any, key_name: str) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError(f"Config '{key_name}' must be a boolean")


def _normalize_fusion_weights(
    raw_weights: dict[str, float],
    plugin_names: Iterable[str],
) -> dict[str, float]:
    names = [str(name).lower() for name in plugin_names]
    if not names:
        return {}

    positive_weights: dict[str, float] = {}
    for name in names:
        value = raw_weights.get(name, 1.0)
        if not isinstance(value, (float, int)):
            continue
        numeric = float(value)
        if numeric > 0:
            positive_weights[name] = numeric

    total = sum(positive_weights.values())
    if total <= 0:
        uniform = 1.0 / float(len(names))
        return {name: uniform for name in names}

    return {
        name: positive_weights.get(name, 0.0) / total
        for name in names
    }
