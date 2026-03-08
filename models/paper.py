"""Data model definitions for paper metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _to_iso(value: datetime | None) -> str | None:
    """Serialize datetime into ISO 8601 string, preserving timezone info."""
    if value is None:
        return None
    return value.isoformat()


def _from_iso(value: str | None) -> datetime | None:
    """Deserialize ISO 8601 string into datetime.

    Naive timestamps (without timezone) are interpreted as UTC to avoid
    mixed timezone semantics across different data sources.
    """
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _utc_now() -> datetime:
    """Return current UTC timestamp as timezone-aware datetime."""
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class PaperMetadata:
    """Unified paper metadata schema persisted in sqlite.

    Fields are designed to be source-agnostic while preserving source-specific
    details via ``extra``.
    """

    id: str
    source: str
    source_id: str
    title: str
    authors: list[str]
    published_at: datetime | None = None
    fetched_at: datetime = field(default_factory=_utc_now)
    abstract: str = ""
    online_url: str = ""
    pdf_url: str | None = None
    local_pdf_path: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    last_accessed_at: datetime = field(default_factory=_utc_now)
    downloaded_at: datetime | None = None

    def to_db_row(self) -> dict[str, Any]:
        """Convert object into sqlite-ready dictionary payload."""
        return {
            "id": self.id,
            "source": self.source,
            "source_id": self.source_id,
            "title": self.title,
            "authors": self.authors,
            "published_at": _to_iso(self.published_at),
            "fetched_at": _to_iso(self.fetched_at),
            "abstract": self.abstract,
            "online_url": self.online_url,
            "pdf_url": self.pdf_url,
            "local_pdf_path": self.local_pdf_path,
            "extra": self.extra,
            "last_accessed_at": _to_iso(self.last_accessed_at),
            "downloaded_at": _to_iso(self.downloaded_at),
        }

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> "PaperMetadata":
        """Build a ``PaperMetadata`` object from sqlite row mapping."""
        return cls(
            id=row["id"],
            source=row["source"],
            source_id=row["source_id"],
            title=row["title"],
            authors=row.get("authors") or [],
            published_at=_from_iso(row.get("published_at")),
            fetched_at=_from_iso(row.get("fetched_at")) or _utc_now(),
            abstract=row.get("abstract") or "",
            online_url=row.get("online_url") or "",
            pdf_url=row.get("pdf_url"),
            local_pdf_path=row.get("local_pdf_path"),
            extra=row.get("extra") or {},
            last_accessed_at=_from_iso(row.get("last_accessed_at")) or _utc_now(),
            downloaded_at=_from_iso(row.get("downloaded_at")),
        )
