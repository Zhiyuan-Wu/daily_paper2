"""Data model definitions for daily paper report management."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from typing import Any


def _normalize_paper_ids(values: list[str] | None) -> list[str]:
    if not values:
        return []
    return [str(value) for value in values]


def _normalize_report_date(value: date | datetime | str) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Field 'report_date' must be a non-empty date/date-time string")

    raw = value.strip()
    try:
        if "T" in raw:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).date().isoformat()
        return date.fromisoformat(raw).isoformat()
    except ValueError as exc:
        raise ValueError("Field 'report_date' must be in ISO format, e.g. 2026-03-11") from exc


def _normalize_generated_at(value: datetime | str | None) -> str:
    if value is None:
        return _utc_now().isoformat()

    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and value.strip():
        raw = value.strip()
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed_date = date.fromisoformat(raw)
            except ValueError as exc:
                raise ValueError(
                    "Field 'generated_at' must be an ISO datetime/date string"
                ) from exc
            dt = datetime.combine(parsed_date, time.min)
    else:
        raise ValueError("Field 'generated_at' must be a datetime or non-empty string")

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


@dataclass(slots=True)
class PaperReportRecord:
    """Report row persisted in sqlite ``report`` table."""

    id: str
    report_date: str
    generated_at: str
    related_paper_ids: list[str] = field(default_factory=list)
    local_md_path: str = ""

    def to_db_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "report_date": _normalize_report_date(self.report_date),
            "generated_at": _normalize_generated_at(self.generated_at),
            "related_paper_ids": json.dumps(
                _normalize_paper_ids(self.related_paper_ids), ensure_ascii=False
            ),
            "local_md_path": self.local_md_path,
        }

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> "PaperReportRecord":
        raw_papers = row.get("related_paper_ids")
        related_paper_ids: list[str] = []
        if isinstance(raw_papers, str) and raw_papers.strip():
            decoded = json.loads(raw_papers)
            if not isinstance(decoded, list):
                raise ValueError("Field 'related_paper_ids' must decode to list")
            related_paper_ids = _normalize_paper_ids(decoded)
        elif isinstance(raw_papers, list):
            related_paper_ids = _normalize_paper_ids(raw_papers)

        report_date = _normalize_report_date(row["report_date"])
        generated_at = _normalize_generated_at(row.get("generated_at"))

        return cls(
            id=row["id"],
            report_date=report_date,
            generated_at=generated_at,
            related_paper_ids=related_paper_ids,
            local_md_path=row.get("local_md_path") or "",
        )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
