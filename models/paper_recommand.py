"""Data models for paper recommendation workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from models.paper import PaperMetadata


@dataclass(slots=True)
class PaperRecommandRequest:
    """Runtime request passed to recommendation plugins."""

    query: str = ""
    top_k: int = 20
    now: datetime | None = None
    plugin_payload: dict[str, Any] = field(default_factory=dict)

    def resolved_now(self) -> datetime:
        value = self.now or datetime.now(timezone.utc)
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


@dataclass(slots=True)
class PaperRecommendation:
    """Final recommendation object returned by the service."""

    paper: PaperMetadata
    score: float
    algorithm_scores: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "paper": self.paper.to_db_row(),
            "score": self.score,
            "algorithm_scores": self.algorithm_scores,
        }
        for key in ["published_at", "fetched_at", "last_accessed_at", "downloaded_at"]:
            value = payload["paper"].get(key)
            if isinstance(value, datetime):
                payload["paper"][key] = value.isoformat()
        return payload
