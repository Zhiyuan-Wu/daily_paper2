"""Data model definitions for extracted paper extend metadata."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


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


def _normalize_list(values: Any) -> list[str]:
    if values is None:
        return []

    raw_items: list[str]
    if isinstance(values, str):
        text = values.strip()
        if not text:
            return []
        if text.startswith("[") and text.endswith("]"):
            try:
                decoded = json.loads(text)
            except json.JSONDecodeError:
                decoded = None
            if isinstance(decoded, list):
                raw_items = [str(item).strip() for item in decoded]
            else:
                raw_items = [segment.strip() for segment in text.split(",")]
        else:
            separators = ["\n", ";", "；", "、", ","]
            normalized = text
            for separator in separators[1:]:
                normalized = normalized.replace(separator, separators[0])
            raw_items = [segment.strip() for segment in normalized.split(separators[0])]
    elif isinstance(values, (list, tuple, set)):
        raw_items = [str(item).strip() for item in values]
    else:
        raw_items = [str(values).strip()]

    deduped: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        if not item:
            continue
        marker = item.lower()
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(item)
    return deduped


@dataclass(slots=True)
class PaperExtendMetadataRecord:
    """Persisted extend metadata row for one paper."""

    paper_id: str
    abstract_cn: str = ""
    affliations: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    github_repo: str = ""
    extracted_at: datetime | None = None

    def __post_init__(self) -> None:
        self.abstract_cn = (self.abstract_cn or "").strip()
        self.affliations = _normalize_list(self.affliations)
        self.keywords = _normalize_list(self.keywords)
        self.github_repo = (self.github_repo or "").strip()

    def to_db_row(self) -> dict[str, Any]:
        return {
            "paper_id": self.paper_id,
            "abstract_cn": self.abstract_cn,
            "affliations": json.dumps(self.affliations, ensure_ascii=False),
            "keywords": json.dumps(self.keywords, ensure_ascii=False),
            "github_repo": self.github_repo,
            "extracted_at": _to_iso(self.extracted_at),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "paper_id": self.paper_id,
            "abstract_cn": self.abstract_cn,
            "affliations": list(self.affliations),
            "keywords": list(self.keywords),
            "github_repo": self.github_repo,
            "extracted_at": _to_iso(self.extracted_at),
        }

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> "PaperExtendMetadataRecord":
        affliations = row.get("affliations") or []
        if isinstance(affliations, str):
            affliations = json.loads(affliations or "[]")

        keywords = row.get("keywords") or []
        if isinstance(keywords, str):
            keywords = json.loads(keywords or "[]")

        return cls(
            paper_id=row["paper_id"],
            abstract_cn=row.get("abstract_cn") or "",
            affliations=affliations,
            keywords=keywords,
            github_repo=row.get("github_repo") or "",
            extracted_at=_from_iso(row.get("extracted_at")),
        )


@dataclass(slots=True)
class PaperExtendMetadataSyncResult:
    """Runtime summary for one extend metadata sync execution."""

    synced_at: datetime
    max_fetched_at: datetime | None
    processed_paper_count: int
    failed_paper_count: int
    llm_model: str
    failures: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "synced_at": _to_iso(self.synced_at),
            "max_fetched_at": _to_iso(self.max_fetched_at),
            "processed_paper_count": self.processed_paper_count,
            "failed_paper_count": self.failed_paper_count,
            "llm_model": self.llm_model,
            "failures": list(self.failures),
        }
