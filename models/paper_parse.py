"""Data model definitions for paper parsing status."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


def _to_iso(value: datetime | None) -> str | None:
    """Serialize datetime into ISO 8601 string."""
    if value is None:
        return None
    return value.isoformat()


def _from_iso(value: str | None) -> datetime | None:
    """Deserialize ISO 8601 string into timezone-aware datetime."""
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass(slots=True)
class PaperParseRecord:
    """SQLite record for parse status and generated markdown path."""

    paper_id: str
    status: str
    local_text_path: str | None = None
    parsed_at: datetime | None = None
    updated_at: datetime | None = None
    error_message: str | None = None
    page_count: int = 0
    ocr_model: str | None = None

    def to_db_row(self) -> dict[str, Any]:
        """Convert object into sqlite-ready mapping."""
        return {
            "paper_id": self.paper_id,
            "status": self.status,
            "local_text_path": self.local_text_path,
            "parsed_at": _to_iso(self.parsed_at),
            "updated_at": _to_iso(self.updated_at),
            "error_message": self.error_message,
            "page_count": self.page_count,
            "ocr_model": self.ocr_model,
        }

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> "PaperParseRecord":
        """Create object from sqlite row mapping."""
        return cls(
            paper_id=row["paper_id"],
            status=row["status"],
            local_text_path=row.get("local_text_path"),
            parsed_at=_from_iso(row.get("parsed_at")),
            updated_at=_from_iso(row.get("updated_at")),
            error_message=row.get("error_message"),
            page_count=int(row.get("page_count") or 0),
            ocr_model=row.get("ocr_model"),
        )
