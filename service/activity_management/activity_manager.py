"""Standalone paper activity management class."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from models.paper_activity import PaperActivityRecord
from service.activity_management.config import get_paper_activity_config
from service.activity_management.repository import PaperActivityRepository


class PaperActivityManager:
    """Manage CRUD operations for paper activity records."""

    def __init__(
        self,
        db_path: str | Path | None = None,
        table_name: str | None = None,
        config_path: str | Path | None = None,
    ) -> None:
        cfg = get_paper_activity_config(config_path)
        resolved_db_path = db_path or _as_str(cfg.get("db_path"), "paper_activity.db_path")
        resolved_table_name = table_name or _as_str(
            cfg.get("table_name") or "activity",
            "paper_activity.table_name",
        )
        self.repo = PaperActivityRepository(resolved_db_path, table_name=resolved_table_name)

    def create_activity(
        self,
        paper_id: str,
        recommendation_records: list[str] | None = None,
        user_notes: str = "",
        ai_report_summary: str = "",
        ai_report_path: str = "",
        like: int = 0,
        *,
        overwrite: bool = False,
    ) -> PaperActivityRecord:
        record = PaperActivityRecord(
            id=paper_id,
            recommendation_records=recommendation_records or [],
            user_notes=user_notes,
            ai_report_summary=ai_report_summary,
            ai_report_path=ai_report_path,
            like=like,
        )
        return self.repo.create(record, overwrite=overwrite)

    def get_activity(self, paper_id: str) -> PaperActivityRecord | None:
        return self.repo.get(paper_id)

    def list_activities(self, *, limit: int = 100, offset: int = 0) -> list[PaperActivityRecord]:
        return self.repo.list(limit=limit, offset=offset)

    def update_activity(
        self,
        paper_id: str,
        *,
        recommendation_records: list[str] | None = None,
        user_notes: str | None = None,
        ai_report_summary: str | None = None,
        ai_report_path: str | None = None,
        like: int | None = None,
    ) -> PaperActivityRecord:
        return self.repo.update_fields(
            paper_id,
            recommendation_records=recommendation_records,
            user_notes=user_notes,
            ai_report_summary=ai_report_summary,
            ai_report_path=ai_report_path,
            like=like,
        )

    def append_recommendation(self, paper_id: str, recommendation_time: str) -> PaperActivityRecord:
        record = self.repo.ensure_activity(paper_id)
        values = list(record.recommendation_records)
        values.append(recommendation_time)
        return self.repo.update_fields(paper_id, recommendation_records=values)

    def delete_activity(self, paper_id: str) -> bool:
        return self.repo.delete(paper_id)

    @staticmethod
    def to_dict(record: PaperActivityRecord) -> dict[str, Any]:
        return asdict(record)

def _as_str(value: Any, key_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Config '{key_name}' must be a non-empty string")
    return value
