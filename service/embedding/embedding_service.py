"""Paper semantic embedding service backed by sqlite-vec and Ollama."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any

from models.paper import PaperMetadata
from models.paper_embedding import PaperEmbeddingRecord, PaperEmbeddingVersion, PaperSearchHit
from service.embedding.config import get_paper_embedding_config
from service.embedding.ollama_client import OllamaEmbeddingClient
from service.embedding.repository import PaperEmbeddingRepository


class PaperEmbeddingService:
    """Manage embedding generation, incremental sync and semantic retrieval."""

    def __init__(
        self,
        db_path: str | Path | None = None,
        embedding_table: str | None = None,
        version_table: str | None = None,
        ollama_endpoint: str | None = None,
        ollama_model: str | None = None,
        ollama_timeout: int | None = None,
        default_top_k: int | None = None,
        default_batch_size: int | None = None,
        config_path: str | Path | None = None,
    ) -> None:
        cfg = get_paper_embedding_config(config_path)
        ollama_cfg = _as_mapping(cfg.get("ollama"), "paper_embedding.ollama")

        self.db_path = Path(db_path or _as_str(cfg.get("db_path"), "paper_embedding.db_path"))
        self.embedding_table = embedding_table or _as_str(
            cfg.get("embedding_table"), "paper_embedding.embedding_table"
        )
        self.version_table = version_table or _as_str(
            cfg.get("version_table"), "paper_embedding.version_table"
        )

        self.default_top_k = (
            default_top_k
            if default_top_k is not None
            else _as_int(cfg.get("default_top_k"), "paper_embedding.default_top_k")
        )
        self.default_batch_size = (
            default_batch_size
            if default_batch_size is not None
            else _as_int(cfg.get("default_batch_size"), "paper_embedding.default_batch_size")
        )

        self.ollama_endpoint = ollama_endpoint or _as_str(
            ollama_cfg.get("endpoint"), "paper_embedding.ollama.endpoint"
        )
        self.ollama_model = ollama_model or _as_str(
            ollama_cfg.get("model"), "paper_embedding.ollama.model"
        )
        self.ollama_timeout = (
            ollama_timeout
            if ollama_timeout is not None
            else _as_int(ollama_cfg.get("timeout_seconds"), "paper_embedding.ollama.timeout_seconds")
        )

        self.client = OllamaEmbeddingClient(
            endpoint=self.ollama_endpoint,
            model=self.ollama_model,
            timeout_seconds=self.ollama_timeout,
        )
        self.repo = PaperEmbeddingRepository(
            self.db_path,
            embedding_table=self.embedding_table,
            version_table=self.version_table,
        )

    def embed_text(self, text: str) -> list[float]:
        """Return one embedding vector for a query text."""
        return self.client.embed(text)

    def embed_texts(self, texts: list[str], batch_size: int | None = None) -> list[list[float]]:
        """Return embedding vectors for query texts."""
        resolved_batch_size = batch_size if batch_size is not None else self.default_batch_size
        return self.client.embed_batch(texts, batch_size=resolved_batch_size)

    def sync_incremental(
        self,
        *,
        limit: int | None = None,
        batch_size: int | None = None,
        force_full: bool = False,
    ) -> PaperEmbeddingVersion:
        """Incrementally compute embeddings by ``papers.fetched_at`` and persist them."""
        latest = self.repo.get_latest_version()
        since = None if force_full else (latest.max_fetched_at if latest else None)
        if force_full:
            self.repo.clear_embeddings()
        if latest and latest.embedding_model and latest.embedding_model != self.ollama_model:
            since = None
            self.repo.clear_embeddings()

        papers = self.repo.list_papers_for_embedding(since_fetched_at=since, limit=limit)
        if not papers:
            max_fetched_at = self.repo.get_max_papers_fetched_at()
            version = PaperEmbeddingVersion(
                id=None,
                synced_at=_utc_now(),
                max_fetched_at=max_fetched_at,
                processed_paper_count=0,
                embedding_model=self.ollama_model,
                embedding_dim=latest.embedding_dim if latest else 0,
            )
            return self.repo.save_version(version)

        resolved_batch_size = batch_size if batch_size is not None else self.default_batch_size
        semantic_texts = [self.compose_semantic_text(paper) for paper in papers]
        vectors = self.embed_texts(semantic_texts, batch_size=resolved_batch_size)

        if len(vectors) != len(papers):
            raise RuntimeError(
                "Embedding vector count mismatch: "
                f"expected={len(papers)} got={len(vectors)}"
            )

        dim = len(vectors[0]) if vectors else 0
        embedded_at = _utc_now()

        records: list[PaperEmbeddingRecord] = []
        for paper, text, vector in zip(papers, semantic_texts, vectors):
            records.append(
                PaperEmbeddingRecord(
                    paper_id=paper.id,
                    meta_text=text,
                    embedding=vector,
                    fetched_at=paper.fetched_at,
                    embedded_at=embedded_at,
                    embedding_model=self.ollama_model,
                    embedding_dim=dim,
                )
            )

        self.repo.upsert_embeddings(records)
        version = PaperEmbeddingVersion(
            id=None,
            synced_at=embedded_at,
            max_fetched_at=max(paper.fetched_at for paper in papers),
            processed_paper_count=len(records),
            embedding_model=self.ollama_model,
            embedding_dim=dim,
        )
        return self.repo.save_version(version)

    def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        published_from: date | datetime | str | None = None,
        published_to: date | datetime | str | None = None,
        fetched_from: date | datetime | str | None = None,
        fetched_to: date | datetime | str | None = None,
    ) -> list[PaperSearchHit]:
        """Search papers by semantic similarity with optional time filters."""
        resolved_top_k = top_k if top_k is not None else self.default_top_k
        query_embedding = self.embed_text(query)
        rows = self.repo.search(
            query_embedding,
            resolved_top_k,
            published_from=_as_datetime(published_from),
            published_to=_as_datetime(published_to, end_of_day=True),
            fetched_from=_as_datetime(fetched_from),
            fetched_to=_as_datetime(fetched_to, end_of_day=True),
        )
        return [PaperSearchHit(paper=paper, distance=distance) for paper, distance in rows]

    def get_latest_version(self) -> PaperEmbeddingVersion | None:
        """Return latest sync checkpoint."""
        return self.repo.get_latest_version()

    @staticmethod
    def compose_semantic_text(paper: PaperMetadata) -> str:
        """Build semantic payload text from paper metadata fields."""
        parts = [
            f"title: {paper.title.strip()}",
            f"authors: {', '.join([x.strip() for x in paper.authors if x.strip()])}",
            f"abstract: {paper.abstract.strip()}",
        ]

        keywords = _collect_keywords(paper)
        if keywords:
            parts.append(f"keywords: {', '.join(keywords)}")

        if paper.source:
            parts.append(f"source: {paper.source}")
        if paper.published_at is not None:
            parts.append(f"published_at: {paper.published_at.isoformat()}")

        return "\n".join(part for part in parts if part.split(":", 1)[1].strip())

    @staticmethod
    def hit_to_dict(hit: PaperSearchHit) -> dict[str, Any]:
        payload = asdict(hit.paper)
        for key in ["published_at", "fetched_at", "last_accessed_at", "downloaded_at"]:
            value = payload.get(key)
            if isinstance(value, datetime):
                payload[key] = value.isoformat()
        return {"paper": payload, "distance": hit.distance}


# Backward-compatible alias for requested naming style.
Paper_Embedding_Service = PaperEmbeddingService


def _collect_keywords(paper: PaperMetadata) -> list[str]:
    values: list[str] = []
    candidate_keys = ("keywords", "keyword", "tags", "category", "categories", "subjects")
    for key in candidate_keys:
        raw = paper.extra.get(key) if isinstance(paper.extra, dict) else None
        if raw is None:
            continue
        if isinstance(raw, str):
            value = raw.strip()
            if value:
                values.extend([item.strip() for item in value.split(",") if item.strip()])
            continue
        if isinstance(raw, (list, tuple, set)):
            values.extend([str(item).strip() for item in raw if str(item).strip()])

    # Keep order stable while removing duplicates.
    deduped: list[str] = []
    seen: set[str] = set()
    for item in values:
        marker = item.lower()
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(item)
    return deduped


def _as_datetime(value: date | datetime | str | None, *, end_of_day: bool = False) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, date):
        dt = datetime.combine(value, time.max if end_of_day else time.min)
        return dt.replace(tzinfo=timezone.utc)

    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)

    if len(value) == 10:  # YYYY-MM-DD
        return datetime.combine(parsed.date(), time.max if end_of_day else time.min, tzinfo=timezone.utc)
    return parsed


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


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
