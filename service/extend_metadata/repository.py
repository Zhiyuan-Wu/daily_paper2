"""SQLite repository for extracted paper extend metadata."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from models.paper import PaperMetadata
from models.paper_extend_metadata import PaperExtendMetadataRecord
from service.common.sqlite_utils import validate_table_name


class PaperExtendMetadataRepository:
    """Persistence layer for extend metadata records."""

    def __init__(self, db_path: str | Path, table_name: str = "extend_metadata") -> None:
        self.db_path = Path(db_path)
        self.table_name = validate_table_name(table_name)
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
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.table_name} (
                    paper_id TEXT PRIMARY KEY,
                    abstract_cn TEXT NOT NULL DEFAULT '',
                    affliations TEXT NOT NULL DEFAULT '[]',
                    keywords TEXT NOT NULL DEFAULT '[]',
                    github_repo TEXT NOT NULL DEFAULT '',
                    extracted_at TEXT NOT NULL,
                    FOREIGN KEY (paper_id) REFERENCES papers(id)
                )
                """
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.table_name}_extracted_at "
                f"ON {self.table_name}(extracted_at)"
            )

    def get_record(self, paper_id: str) -> PaperExtendMetadataRecord | None:
        with self._conn() as conn:
            row = conn.execute(
                f"SELECT * FROM {self.table_name} WHERE paper_id = ?",
                (paper_id,),
            ).fetchone()
            if not row:
                return None
            return PaperExtendMetadataRecord.from_db_row(dict(row))

    def upsert_record(self, record: PaperExtendMetadataRecord) -> None:
        row = record.to_db_row()
        with self._conn() as conn:
            conn.execute(
                f"""
                INSERT INTO {self.table_name} (
                    paper_id, abstract_cn, affliations, keywords, github_repo, extracted_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(paper_id) DO UPDATE SET
                    abstract_cn=excluded.abstract_cn,
                    affliations=excluded.affliations,
                    keywords=excluded.keywords,
                    github_repo=excluded.github_repo,
                    extracted_at=excluded.extracted_at
                """,
                (
                    row["paper_id"],
                    row["abstract_cn"],
                    row["affliations"],
                    row["keywords"],
                    row["github_repo"],
                    row["extracted_at"],
                ),
            )

    def list_papers_for_extension(self, limit: int | None = None) -> list[PaperMetadata]:
        sql = f"""
            SELECT p.*
            FROM papers p
            LEFT JOIN {self.table_name} e ON e.paper_id = p.id
            WHERE p.fetched_at IS NOT NULL AND e.paper_id IS NULL
            ORDER BY p.fetched_at ASC, p.id ASC
        """
        params: tuple[object, ...] = ()
        if limit is not None:
            sql += " LIMIT ?"
            params = (limit,)

        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [self._row_to_metadata(row) for row in rows]

    def get_max_papers_fetched_at(self) -> datetime | None:
        with self._conn() as conn:
            row = conn.execute("SELECT MAX(fetched_at) AS max_fetched_at FROM papers").fetchone()
            if not row or not row["max_fetched_at"]:
                return None
            return _from_iso(row["max_fetched_at"])

    def count_records(self) -> int:
        with self._conn() as conn:
            row = conn.execute(f"SELECT COUNT(*) AS c FROM {self.table_name}").fetchone()
            return int((row or {"c": 0})["c"])

    @staticmethod
    def _row_to_metadata(row: sqlite3.Row) -> PaperMetadata:
        data = dict(row)
        data["authors"] = json.loads(data.get("authors") or "[]")
        data["extra"] = json.loads(data.get("extra") or "{}")
        return PaperMetadata.from_db_row(data)


def _from_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
