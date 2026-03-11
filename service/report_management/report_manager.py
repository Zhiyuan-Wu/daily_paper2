"""Standalone daily report management class."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models.paper_report import PaperReportRecord
from service.report_management.config import get_paper_report_config
from service.report_management.repository import PaperReportRepository


class DailyReportManager:
    """Manage CRUD operations for daily report records."""

    def __init__(
        self,
        db_path: str | Path | None = None,
        table_name: str | None = None,
        config_path: str | Path | None = None,
    ) -> None:
        cfg = get_paper_report_config(config_path)
        resolved_db_path = db_path or _as_str(cfg.get("db_path"), "paper_report.db_path")
        resolved_table_name = table_name or _as_str(
            cfg.get("table_name") or "report",
            "paper_report.table_name",
        )
        self.repo = PaperReportRepository(resolved_db_path, table_name=resolved_table_name)

    def create_report(
        self,
        report_id: str,
        report_date: str,
        generated_at: str | None = None,
        related_paper_ids: list[str] | None = None,
        local_md_path: str = "",
        *,
        overwrite: bool = False,
    ) -> PaperReportRecord:
        record = PaperReportRecord(
            id=report_id,
            report_date=report_date,
            generated_at=generated_at or datetime.now(timezone.utc).isoformat(),
            related_paper_ids=related_paper_ids or [],
            local_md_path=local_md_path,
        )
        return self.repo.create(record, overwrite=overwrite)

    def get_report(self, report_id: str) -> PaperReportRecord | None:
        return self.repo.get(report_id)

    def list_reports(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        report_date: str | None = None,
    ) -> list[PaperReportRecord]:
        return self.repo.list(limit=limit, offset=offset, report_date=report_date)

    def update_report(
        self,
        report_id: str,
        *,
        report_date: str | None = None,
        generated_at: str | None = None,
        related_paper_ids: list[str] | None = None,
        local_md_path: str | None = None,
    ) -> PaperReportRecord:
        return self.repo.update_fields(
            report_id,
            report_date=report_date,
            generated_at=generated_at,
            related_paper_ids=related_paper_ids,
            local_md_path=local_md_path,
        )

    def delete_report(self, report_id: str) -> bool:
        return self.repo.delete(report_id)

    @staticmethod
    def to_dict(record: PaperReportRecord) -> dict[str, Any]:
        return asdict(record)


# Backward-compatible alias for class naming preferences.
Paper_Report_Manager = DailyReportManager


def _as_str(value: Any, key_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Config '{key_name}' must be a non-empty string")
    return value
