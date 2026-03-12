"""Data model definitions for paper embedding records and search hits."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from models.paper import PaperMetadata


def _to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _from_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass(slots=True)
class PaperEmbeddingRecord:
    """Persisted semantic embedding row for one paper."""

    paper_id: str
    meta_text: str
    embedding: list[float]
    fetched_at: datetime
    embedded_at: datetime
    embedding_model: str
    embedding_dim: int

    def to_db_row(self) -> dict[str, Any]:
        return {
            "paper_id": self.paper_id,
            "meta_text": self.meta_text,
            "embedding": self.embedding,
            "fetched_at": _to_iso(self.fetched_at),
            "embedded_at": _to_iso(self.embedded_at),
            "embedding_model": self.embedding_model,
            "embedding_dim": self.embedding_dim,
        }

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> "PaperEmbeddingRecord":
        raw_embedding = row.get("embedding")
        embedding = [float(v) for v in raw_embedding] if isinstance(raw_embedding, list) else []
        return cls(
            paper_id=row["paper_id"],
            meta_text=row["meta_text"],
            embedding=embedding,
            fetched_at=_from_iso(row.get("fetched_at")) or datetime.now(timezone.utc),
            embedded_at=_from_iso(row.get("embedded_at")) or datetime.now(timezone.utc),
            embedding_model=row.get("embedding_model") or "",
            embedding_dim=int(row.get("embedding_dim") or 0),
        )


@dataclass(slots=True)
class PaperEmbeddingVersion:
    """Version checkpoint for incremental embedding sync."""

    id: int | None
    synced_at: datetime
    max_fetched_at: datetime | None
    processed_paper_count: int
    embedding_model: str
    embedding_dim: int

    def to_db_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "synced_at": _to_iso(self.synced_at),
            "max_fetched_at": _to_iso(self.max_fetched_at),
            "processed_paper_count": self.processed_paper_count,
            "embedding_model": self.embedding_model,
            "embedding_dim": self.embedding_dim,
        }

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> "PaperEmbeddingVersion":
        return cls(
            id=row.get("id"),
            synced_at=_from_iso(row.get("synced_at")) or datetime.now(timezone.utc),
            max_fetched_at=_from_iso(row.get("max_fetched_at")),
            processed_paper_count=int(row.get("processed_paper_count") or 0),
            embedding_model=row.get("embedding_model") or "",
            embedding_dim=int(row.get("embedding_dim") or 0),
        )


@dataclass(slots=True)
class PaperSearchHit:
    """Semantic search hit with distance and paper metadata."""

    paper: PaperMetadata
    distance: float

    def to_dict(self) -> dict[str, Any]:
        return {"paper": self.paper.to_db_row(), "distance": self.distance}
