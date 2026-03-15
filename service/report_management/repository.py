"""SQLite repository for daily report data."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from models.paper_report import PaperReportRecord
from service.common.sqlite_utils import validate_table_name


class PaperReportRepository:
    """Persistence layer for ``report`` table CRUD."""

    def __init__(self, db_path: str | Path, table_name: str = "report") -> None:
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
                f"""
                CREATE TABLE IF NOT EXISTS {self.table_name} (
                    id TEXT PRIMARY KEY,
                    report_date TEXT NOT NULL,
                    generated_at TEXT NOT NULL,
                    related_paper_ids TEXT NOT NULL DEFAULT '[]',
                    local_md_path TEXT NOT NULL DEFAULT ''
                )
                """
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.table_name}_report_date ON {self.table_name}(report_date)"
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.table_name}_generated_at ON {self.table_name}(generated_at)"
            )

    def create(self, record: PaperReportRecord, *, overwrite: bool = False) -> PaperReportRecord:
        row = record.to_db_row()
        with self._conn() as conn:
            if overwrite:
                conn.execute(
                    f"""
                    INSERT INTO {self.table_name} (
                        id, report_date, generated_at, related_paper_ids, local_md_path
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        report_date=excluded.report_date,
                        generated_at=excluded.generated_at,
                        related_paper_ids=excluded.related_paper_ids,
                        local_md_path=excluded.local_md_path
                    """,
                    (
                        row["id"],
                        row["report_date"],
                        row["generated_at"],
                        row["related_paper_ids"],
                        row["local_md_path"],
                    ),
                )
                created = self.get(record.id)
                if not created:
                    raise RuntimeError("report row missing after upsert")
                return created

            conn.execute(
                f"""
                INSERT INTO {self.table_name} (
                    id, report_date, generated_at, related_paper_ids, local_md_path
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    row["report_date"],
                    row["generated_at"],
                    row["related_paper_ids"],
                    row["local_md_path"],
                ),
            )
        return PaperReportRecord.from_db_row(row)

    def get(self, report_id: str) -> PaperReportRecord | None:
        with self._conn() as conn:
            row = conn.execute(
                f"SELECT * FROM {self.table_name} WHERE id = ?",
                (report_id,),
            ).fetchone()
            if not row:
                return None
            return PaperReportRecord.from_db_row(dict(row))

    def list(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        report_date: str | None = None,
    ) -> list[PaperReportRecord]:
        sql = f"SELECT * FROM {self.table_name}"
        params: list[Any] = []
        if report_date is not None:
            sql += " WHERE report_date = ?"
            params.append(report_date)
        sql += " ORDER BY report_date DESC, generated_at DESC, id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [PaperReportRecord.from_db_row(dict(row)) for row in rows]

    def update_fields(
        self,
        report_id: str,
        *,
        report_date: str | None = None,
        generated_at: str | None = None,
        related_paper_ids: list[str] | None = None,
        local_md_path: str | None = None,
    ) -> PaperReportRecord:
        current = self.get(report_id)
        if current is None:
            raise KeyError(f"Report not found: {report_id}")

        if report_date is not None:
            current.report_date = report_date
        if generated_at is not None:
            current.generated_at = generated_at
        if related_paper_ids is not None:
            current.related_paper_ids = related_paper_ids
        if local_md_path is not None:
            current.local_md_path = local_md_path

        row = current.to_db_row()
        with self._conn() as conn:
            conn.execute(
                f"""
                UPDATE {self.table_name}
                SET report_date = ?, generated_at = ?, related_paper_ids = ?, local_md_path = ?
                WHERE id = ?
                """,
                (
                    row["report_date"],
                    row["generated_at"],
                    row["related_paper_ids"],
                    row["local_md_path"],
                    report_id,
                ),
            )
        updated = self.get(report_id)
        if not updated:
            raise RuntimeError(f"Report unexpectedly missing after update: {report_id}")
        return updated

    def delete(self, report_id: str) -> bool:
        with self._conn() as conn:
            result = conn.execute(
                f"DELETE FROM {self.table_name} WHERE id = ?",
                (report_id,),
            )
            return result.rowcount > 0

    def raw_row(self, report_id: str) -> dict[str, Any] | None:
        """Testing helper: read row with sqlite-level raw values."""
        with self._conn() as conn:
            row = conn.execute(
                f"SELECT * FROM {self.table_name} WHERE id = ?",
                (report_id,),
            ).fetchone()
            return dict(row) if row else None
