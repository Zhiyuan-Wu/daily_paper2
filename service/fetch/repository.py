"""SQLite repository for paper metadata."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from models.paper import PaperMetadata


class PaperRepository:
    """Persistence layer that handles all sqlite interactions.

    The repository isolates SQL operations from business logic in ``PaperFetch``.
    """

    def __init__(self, db_path: str | Path) -> None:
        """Initialize repository and ensure schema exists."""
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        """Yield a short-lived sqlite connection with auto-commit semantics."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Create tables and indexes when they do not exist."""
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS papers (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    authors TEXT NOT NULL,
                    published_at TEXT,
                    fetched_at TEXT NOT NULL,
                    abstract TEXT,
                    online_url TEXT,
                    pdf_url TEXT,
                    local_pdf_path TEXT,
                    extra TEXT,
                    last_accessed_at TEXT NOT NULL,
                    downloaded_at TEXT,
                    UNIQUE(source, source_id)
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_papers_source ON papers(source)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_papers_published_at ON papers(published_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_papers_local_pdf ON papers(local_pdf_path)")

    def upsert_papers(self, papers: list[PaperMetadata]) -> None:
        """Insert or update metadata entries.

        Existing rows are refreshed with the latest online fields while keeping
        locally managed download fields unless explicitly updated by download APIs.
        """
        if not papers:
            return
        with self._conn() as conn:
            for paper in papers:
                row = paper.to_db_row()
                conn.execute(
                    """
                    INSERT INTO papers (
                        id, source, source_id, title, authors, published_at, fetched_at,
                        abstract, online_url, pdf_url, local_pdf_path, extra,
                        last_accessed_at, downloaded_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        source=excluded.source,
                        source_id=excluded.source_id,
                        title=excluded.title,
                        authors=excluded.authors,
                        published_at=excluded.published_at,
                        fetched_at=excluded.fetched_at,
                        abstract=excluded.abstract,
                        online_url=excluded.online_url,
                        pdf_url=excluded.pdf_url,
                        extra=excluded.extra,
                        last_accessed_at=excluded.last_accessed_at
                    """,
                    (
                        row["id"],
                        row["source"],
                        row["source_id"],
                        row["title"],
                        json.dumps(row["authors"], ensure_ascii=False),
                        row["published_at"],
                        row["fetched_at"],
                        row["abstract"],
                        row["online_url"],
                        row["pdf_url"],
                        row["local_pdf_path"],
                        json.dumps(row["extra"], ensure_ascii=False),
                        row["last_accessed_at"],
                        row["downloaded_at"],
                    ),
                )

    def get_by_id(self, paper_id: str) -> PaperMetadata | None:
        """Get one paper by internal ``id``."""
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
            if not row:
                return None
            return self._row_to_metadata(row)

    def get_by_source_id(self, source: str, source_id: str) -> PaperMetadata | None:
        """Get one paper by ``source`` + ``source_id`` pair."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM papers WHERE source = ? AND source_id = ?", (source, source_id)
            ).fetchone()
            if not row:
                return None
            return self._row_to_metadata(row)

    def search_local(
        self,
        source: str | None = None,
        keywords: list[str] | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        has_pdf: bool | None = None,
        limit: int | None = None,
    ) -> list[PaperMetadata]:
        """Search metadata in sqlite with optional filters.

        Notes:
            - Keyword filter is an ``AND`` relationship between keywords.
            - Each keyword is matched against title OR abstract.
        """
        conditions: list[str] = []
        params: list[object] = []

        if source:
            conditions.append("source = ?")
            params.append(source)

        if start_date:
            conditions.append("published_at >= ?")
            params.append(start_date.isoformat())

        if end_date:
            conditions.append("published_at <= ?")
            params.append(end_date.isoformat())

        if has_pdf is True:
            conditions.append("local_pdf_path IS NOT NULL")
        elif has_pdf is False:
            conditions.append("local_pdf_path IS NULL")

        if keywords:
            for keyword in keywords:
                conditions.append("(LOWER(title) LIKE ? OR LOWER(abstract) LIKE ?)")
                pattern = f"%{keyword.lower()}%"
                params.extend([pattern, pattern])

        where = ""
        if conditions:
            where = "WHERE " + " AND ".join(conditions)

        if limit is None:
            raise ValueError("search_local requires explicit 'limit' from caller")

        query = f"""
            SELECT * FROM papers
            {where}
            ORDER BY COALESCE(published_at, fetched_at) DESC
            LIMIT ?
        """
        params.append(limit)

        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_metadata(row) for row in rows]

    def update_download_path(self, paper_id: str, local_path: str) -> None:
        """Store local file path and set download/access timestamps."""
        now = _utc_now().isoformat()
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE papers
                SET local_pdf_path = ?, downloaded_at = ?, last_accessed_at = ?
                WHERE id = ?
                """,
                (local_path, now, now, paper_id),
            )

    def touch_access(self, paper_id: str) -> None:
        """Refresh ``last_accessed_at`` for LRU ordering."""
        with self._conn() as conn:
            conn.execute(
                "UPDATE papers SET last_accessed_at = ? WHERE id = ?",
                (_utc_now().isoformat(), paper_id),
            )

    def list_downloaded_by_lru(self) -> list[PaperMetadata]:
        """Return downloaded papers ordered from oldest to newest access."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM papers
                WHERE local_pdf_path IS NOT NULL
                ORDER BY COALESCE(last_accessed_at, downloaded_at, fetched_at) ASC
                """
            ).fetchall()
            return [self._row_to_metadata(row) for row in rows]

    def clear_download_path(self, paper_id: str) -> None:
        """Clear local path after LRU eviction."""
        with self._conn() as conn:
            conn.execute(
                "UPDATE papers SET local_pdf_path = NULL WHERE id = ?",
                (paper_id,),
            )

    @staticmethod
    def _row_to_metadata(row: sqlite3.Row) -> PaperMetadata:
        """Convert sqlite row into ``PaperMetadata`` with JSON decoding."""
        data = dict(row)
        data["authors"] = json.loads(data.get("authors") or "[]")
        data["extra"] = json.loads(data.get("extra") or "{}")
        return PaperMetadata.from_db_row(data)


def _utc_now() -> datetime:
    """Return timezone-aware UTC timestamp for persistence timestamps."""
    return datetime.now(timezone.utc)
