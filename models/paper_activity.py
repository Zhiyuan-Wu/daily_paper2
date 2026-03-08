"""Data model definitions for paper activity management."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


def _normalize_recommendations(values: list[str] | None) -> list[str]:
    if not values:
        return []
    return [str(value) for value in values]


@dataclass(slots=True)
class PaperActivityRecord:
    """Activity row persisted in sqlite ``activity`` table."""

    id: str
    recommendation_records: list[str] = field(default_factory=list)
    user_notes: str = ""
    ai_report_summary: str = ""
    ai_report_path: str = ""

    def to_db_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "recommendation_records": json.dumps(
                _normalize_recommendations(self.recommendation_records), ensure_ascii=False
            ),
            "user_notes": self.user_notes,
            "ai_report_summary": self.ai_report_summary,
            "ai_report_path": self.ai_report_path,
        }

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> "PaperActivityRecord":
        raw_recommendations = row.get("recommendation_records")
        recommendations: list[str] = []
        if isinstance(raw_recommendations, str) and raw_recommendations.strip():
            decoded = json.loads(raw_recommendations)
            if not isinstance(decoded, list):
                raise ValueError("Field 'recommendation_records' must decode to list")
            recommendations = _normalize_recommendations(decoded)
        elif isinstance(raw_recommendations, list):
            recommendations = _normalize_recommendations(raw_recommendations)

        return cls(
            id=row["id"],
            recommendation_records=recommendations,
            user_notes=row.get("user_notes") or "",
            ai_report_summary=row.get("ai_report_summary") or "",
            ai_report_path=row.get("ai_report_path") or "",
        )
