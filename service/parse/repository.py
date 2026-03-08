"""SQLite repository for paper parsing status."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from models.paper_parse import PaperParseRecord


class PaperParseRepository:
    """Persistence layer for parse status and markdown output path."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS paper_parses (
                    paper_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    local_text_path TEXT,
                    parsed_at TEXT,
                    updated_at TEXT NOT NULL,
                    error_message TEXT,
                    page_count INTEGER NOT NULL DEFAULT 0,
                    ocr_model TEXT,
                    FOREIGN KEY (paper_id) REFERENCES papers(id)
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_paper_parses_status ON paper_parses(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_paper_parses_parsed_at ON paper_parses(parsed_at)")
            self._ensure_papers_local_text_column(conn)

    @staticmethod
    def _ensure_papers_local_text_column(conn: sqlite3.Connection) -> None:
        """Add ``papers.local_text_path`` when absent for compatibility."""
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='papers'"
        ).fetchone()
        if not row:
            return

        columns = conn.execute("PRAGMA table_info(papers)").fetchall()
        existing = {column["name"] for column in columns}
        if "local_text_path" not in existing:
            conn.execute("ALTER TABLE papers ADD COLUMN local_text_path TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_papers_local_text ON papers(local_text_path)")

    def paper_exists(self, paper_id: str) -> bool:
        with self._conn() as conn:
            row = conn.execute("SELECT 1 FROM papers WHERE id = ? LIMIT 1", (paper_id,)).fetchone()
            return row is not None

    def get_paper_pdf_path(self, paper_id: str) -> str | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT local_pdf_path FROM papers WHERE id = ?",
                (paper_id,),
            ).fetchone()
            if not row:
                return None
            return row["local_pdf_path"]

    def save_parse_success(
        self,
        *,
        paper_id: str,
        local_text_path: str,
        page_count: int,
        ocr_model: str,
    ) -> None:
        now = _utc_now().isoformat()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO paper_parses (
                    paper_id, status, local_text_path, parsed_at, updated_at,
                    error_message, page_count, ocr_model
                ) VALUES (?, 'success', ?, ?, ?, NULL, ?, ?)
                ON CONFLICT(paper_id) DO UPDATE SET
                    status='success',
                    local_text_path=excluded.local_text_path,
                    parsed_at=excluded.parsed_at,
                    updated_at=excluded.updated_at,
                    error_message=NULL,
                    page_count=excluded.page_count,
                    ocr_model=excluded.ocr_model
                """,
                (paper_id, local_text_path, now, now, page_count, ocr_model),
            )
            conn.execute(
                "UPDATE papers SET local_text_path = ? WHERE id = ?",
                (local_text_path, paper_id),
            )

    def save_parse_failure(self, *, paper_id: str, error_message: str, ocr_model: str) -> None:
        now = _utc_now().isoformat()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO paper_parses (
                    paper_id, status, local_text_path, parsed_at, updated_at,
                    error_message, page_count, ocr_model
                ) VALUES (?, 'failed', NULL, NULL, ?, ?, 0, ?)
                ON CONFLICT(paper_id) DO UPDATE SET
                    status='failed',
                    updated_at=excluded.updated_at,
                    error_message=excluded.error_message,
                    ocr_model=excluded.ocr_model
                """,
                (paper_id, now, error_message, ocr_model),
            )

    def get_parse_record(self, paper_id: str) -> PaperParseRecord | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM paper_parses WHERE paper_id = ?",
                (paper_id,),
            ).fetchone()
            if not row:
                return None
            return PaperParseRecord.from_db_row(dict(row))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
