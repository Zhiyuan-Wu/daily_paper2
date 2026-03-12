"""SQLite repository for paper activity data."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from models.paper_activity import PaperActivityRecord


class PaperActivityRepository:
    """Persistence layer for ``activity`` table CRUD."""

    def __init__(self, db_path: str | Path, table_name: str = "activity") -> None:
        self.db_path = Path(db_path)
        self.table_name = table_name
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
                f"""
                CREATE TABLE IF NOT EXISTS {self.table_name} (
                    id TEXT PRIMARY KEY,
                    recommendation_records TEXT NOT NULL DEFAULT '[]',
                    user_notes TEXT NOT NULL DEFAULT '',
                    ai_report_summary TEXT NOT NULL DEFAULT '',
                    ai_report_path TEXT NOT NULL DEFAULT '',
                    "like" INTEGER NOT NULL DEFAULT 0 CHECK("like" IN (-1, 0, 1))
                )
                """
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.table_name}_ai_report_path ON {self.table_name}(ai_report_path)"
            )

    def create(self, record: PaperActivityRecord, *, overwrite: bool = False) -> PaperActivityRecord:
        row = record.to_db_row()
        with self._conn() as conn:
            if overwrite:
                conn.execute(
                    f"""
                    INSERT INTO {self.table_name} (
                        id, recommendation_records, user_notes, ai_report_summary, ai_report_path, "like"
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        recommendation_records=excluded.recommendation_records,
                        user_notes=excluded.user_notes,
                        ai_report_summary=excluded.ai_report_summary,
                        ai_report_path=excluded.ai_report_path,
                        "like"=excluded."like"
                    """,
                    (
                        row["id"],
                        row["recommendation_records"],
                        row["user_notes"],
                        row["ai_report_summary"],
                        row["ai_report_path"],
                        row["like"],
                    ),
                )
            else:
                conn.execute(
                    f"""
                    INSERT INTO {self.table_name} (
                        id, recommendation_records, user_notes, ai_report_summary, ai_report_path, "like"
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["id"],
                        row["recommendation_records"],
                        row["user_notes"],
                        row["ai_report_summary"],
                        row["ai_report_path"],
                        row["like"],
                    ),
                )

        if overwrite:
            created = self.get(record.id)
            if not created:
                raise RuntimeError("activity row missing after upsert")
            return created
        return record

    def get(self, paper_id: str) -> PaperActivityRecord | None:
        with self._conn() as conn:
            row = conn.execute(
                f"SELECT * FROM {self.table_name} WHERE id = ?",
                (paper_id,),
            ).fetchone()
            if not row:
                return None
            return PaperActivityRecord.from_db_row(dict(row))

    def list(self, *, limit: int = 100, offset: int = 0) -> list[PaperActivityRecord]:
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM {self.table_name} ORDER BY id ASC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            return [PaperActivityRecord.from_db_row(dict(row)) for row in rows]

    def update_fields(
        self,
        paper_id: str,
        *,
        recommendation_records: list[str] | None = None,
        user_notes: str | None = None,
        ai_report_summary: str | None = None,
        ai_report_path: str | None = None,
        like: int | None = None,
    ) -> PaperActivityRecord:
        current = self.get(paper_id)
        if current is None:
            raise KeyError(f"Activity not found: {paper_id}")

        if recommendation_records is not None:
            current.recommendation_records = recommendation_records
        if user_notes is not None:
            current.user_notes = user_notes
        if ai_report_summary is not None:
            current.ai_report_summary = ai_report_summary
        if ai_report_path is not None:
            current.ai_report_path = ai_report_path
        if like is not None:
            current.like = like

        row = current.to_db_row()
        with self._conn() as conn:
            conn.execute(
                f"""
                UPDATE {self.table_name}
                SET recommendation_records = ?, user_notes = ?, ai_report_summary = ?, ai_report_path = ?, "like" = ?
                WHERE id = ?
                """,
                (
                    row["recommendation_records"],
                    row["user_notes"],
                    row["ai_report_summary"],
                    row["ai_report_path"],
                    row["like"],
                    paper_id,
                ),
            )
        updated = self.get(paper_id)
        if not updated:
            raise RuntimeError(f"Activity unexpectedly missing after update: {paper_id}")
        return updated

    def delete(self, paper_id: str) -> bool:
        with self._conn() as conn:
            result = conn.execute(
                f"DELETE FROM {self.table_name} WHERE id = ?",
                (paper_id,),
            )
            return result.rowcount > 0

    def ensure_activity(self, paper_id: str) -> PaperActivityRecord:
        existing = self.get(paper_id)
        if existing:
            return existing
        return self.create(PaperActivityRecord(id=paper_id))

    def raw_row(self, paper_id: str) -> dict[str, Any] | None:
        """Testing helper: read row with sqlite-level raw values."""
        with self._conn() as conn:
            row = conn.execute(
                f"SELECT * FROM {self.table_name} WHERE id = ?",
                (paper_id,),
            ).fetchone()
            return dict(row) if row else None
