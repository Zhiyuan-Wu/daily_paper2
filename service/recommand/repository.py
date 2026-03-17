"""SQLite repository for recommendation module."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from models.paper import PaperMetadata
from models.paper_activity import PaperActivityRecord
from service.common.sqlite_utils import validate_table_name


class PaperRecommandRepository:
    """Read-only repository for recommendation strategies."""

    def __init__(
        self,
        db_path: str | Path,
        *,
        paper_table: str = "papers",
        activity_table: str = "activity",
        extend_metadata_table: str = "extend_metadata",
    ) -> None:
        self.db_path = Path(db_path)
        self.paper_table = validate_table_name(paper_table)
        self.activity_table = validate_table_name(activity_table)
        self.extend_metadata_table = validate_table_name(extend_metadata_table)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def table_exists(self, table_name: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
                (table_name,),
            ).fetchone()
            return row is not None

    def list_papers(self, *, fetched_from: datetime | None = None) -> list[PaperMetadata]:
        if not self.table_exists(self.paper_table):
            return []
        params: list[object] = []
        where_sql = ""
        if fetched_from is not None:
            where_sql = "WHERE fetched_at >= ?"
            params.append(fetched_from.isoformat())
        with self._conn() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM {self.paper_table}
                {where_sql}
                ORDER BY fetched_at DESC, id ASC
                """,
                params,
            ).fetchall()
            return [self._row_to_paper(row) for row in rows]

    def get_papers_by_ids(self, paper_ids: list[str]) -> dict[str, PaperMetadata]:
        if not paper_ids or not self.table_exists(self.paper_table):
            return {}

        placeholders = ", ".join(["?"] * len(paper_ids))
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM {self.paper_table} WHERE id IN ({placeholders})",
                paper_ids,
            ).fetchall()
            result: dict[str, PaperMetadata] = {}
            for row in rows:
                paper = self._row_to_paper(row)
                result[paper.id] = paper
            return result

    def list_activities(self) -> list[PaperActivityRecord]:
        if not self.table_exists(self.activity_table):
            return []
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM {self.activity_table} ORDER BY id ASC"
            ).fetchall()
            return [self._row_to_activity(row) for row in rows]

    def get_affiliations_by_paper_ids(self, paper_ids: list[str]) -> dict[str, list[str]]:
        if not paper_ids or not self.table_exists(self.extend_metadata_table):
            return {}

        placeholders = ", ".join(["?"] * len(paper_ids))
        with self._conn() as conn:
            rows = conn.execute(
                f"""
                SELECT paper_id, affliations
                FROM {self.extend_metadata_table}
                WHERE paper_id IN ({placeholders})
                """,
                paper_ids,
            ).fetchall()
            result: dict[str, list[str]] = {}
            for row in rows:
                paper_id = row["paper_id"]
                if not isinstance(paper_id, str) or not paper_id.strip():
                    continue
                result[paper_id] = _safe_json_list(row["affliations"])
            return result

    @staticmethod
    def _row_to_paper(row: sqlite3.Row) -> PaperMetadata:
        data = dict(row)
        data["authors"] = _safe_json_list(data.get("authors"))
        data["extra"] = _safe_json_dict(data.get("extra"))
        return PaperMetadata.from_db_row(data)

    @staticmethod
    def _row_to_activity(row: sqlite3.Row) -> PaperActivityRecord:
        data = dict(row)
        raw_records = data.get("recommendation_records")
        if isinstance(raw_records, str):
            try:
                parsed = json.loads(raw_records)
            except json.JSONDecodeError:
                parsed = []
            data["recommendation_records"] = parsed if isinstance(parsed, list) else []
        return PaperActivityRecord.from_db_row(data)


def _safe_json_list(value: object) -> list[str]:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def _safe_json_dict(value: object) -> dict[str, object]:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return parsed
    if isinstance(value, dict):
        return value
    return {}
