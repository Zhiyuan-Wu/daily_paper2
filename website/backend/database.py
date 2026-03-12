"""SQLite data access helpers for website backend."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from service.activity_management.repository import PaperActivityRepository
from service.report_management.repository import PaperReportRepository


class SQLiteDataStore:
    """Read/write access to papers, activity, and report tables."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Ensure required tables/indexes exist.
        PaperActivityRepository(self.db_path)
        PaperReportRepository(self.db_path)
        self._ensure_papers_compat_columns()

    @contextmanager
    def conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def paper_exists(self, paper_id: str) -> bool:
        with self.conn() as conn:
            row = conn.execute("SELECT 1 FROM papers WHERE id = ? LIMIT 1", (paper_id,)).fetchone()
            return row is not None

    def _ensure_papers_compat_columns(self) -> None:
        with self.conn() as conn:
            table_row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='papers'"
            ).fetchone()
            if not table_row:
                return

            columns = conn.execute("PRAGMA table_info(papers)").fetchall()
            existing = {column["name"] for column in columns}
            if "local_text_path" not in existing:
                conn.execute("ALTER TABLE papers ADD COLUMN local_text_path TEXT")
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_papers_local_text ON papers(local_text_path)"
                )

    def get_report_by_date(self, report_date: str) -> dict[str, Any] | None:
        with self.conn() as conn:
            row = conn.execute(
                """
                SELECT id, report_date, generated_at, related_paper_ids, local_md_path
                FROM report
                WHERE report_date = ?
                ORDER BY generated_at DESC, id DESC
                LIMIT 1
                """,
                (report_date,),
            ).fetchone()
        return _report_row_to_payload(row) if row else None

    def get_report(self, report_id: str) -> dict[str, Any] | None:
        with self.conn() as conn:
            row = conn.execute(
                """
                SELECT id, report_date, generated_at, related_paper_ids, local_md_path
                FROM report
                WHERE id = ?
                """,
                (report_id,),
            ).fetchone()
        return _report_row_to_payload(row) if row else None

    def list_explore_papers(
        self,
        *,
        page: int,
        page_size: int,
        keyword: str | None,
        source: str | None,
    ) -> dict[str, Any]:
        where_clauses: list[str] = []
        params: list[Any] = []

        if source:
            where_clauses.append("p.source = ?")
            params.append(source)

        if keyword:
            like = f"%{keyword.strip().lower()}%"
            where_clauses.append(
                """
                (
                    LOWER(p.title) LIKE ?
                    OR LOWER(COALESCE(p.abstract, '')) LIKE ?
                    OR LOWER(COALESCE(p.extra, '')) LIKE ?
                )
                """
            )
            params.extend([like, like, like])

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        base_sql = f"""
            FROM papers p
            LEFT JOIN activity a ON a.id = p.id
            {where_sql}
        """

        with self.conn() as conn:
            total_row = conn.execute(f"SELECT COUNT(*) {base_sql}", params).fetchone()
            total = int(total_row[0]) if total_row else 0

            offset = (page - 1) * page_size
            rows = conn.execute(
                f"""
                SELECT
                    p.id,
                    p.title,
                    p.authors,
                    p.published_at,
                    p.source,
                    p.online_url,
                    p.pdf_url,
                    p.abstract,
                    p.extra,
                    p.local_pdf_path,
                    p.local_text_path,
                    a.recommendation_records,
                    a.user_notes,
                    a.ai_report_summary,
                    a.ai_report_path,
                    a."like" AS activity_like
                {base_sql}
                ORDER BY COALESCE(p.published_at, '') DESC, p.id DESC
                LIMIT ? OFFSET ?
                """,
                [*params, page_size, offset],
            ).fetchall()

        return {
            "items": [_paper_row_to_payload(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def get_paper_detail(self, paper_id: str) -> dict[str, Any] | None:
        with self.conn() as conn:
            row = conn.execute(
                """
                SELECT
                    p.id,
                    p.title,
                    p.authors,
                    p.published_at,
                    p.source,
                    p.online_url,
                    p.pdf_url,
                    p.abstract,
                    p.extra,
                    p.local_pdf_path,
                    p.local_text_path,
                    a.recommendation_records,
                    a.user_notes,
                    a.ai_report_summary,
                    a.ai_report_path,
                    a."like" AS activity_like
                FROM papers p
                LEFT JOIN activity a ON a.id = p.id
                WHERE p.id = ?
                """,
                (paper_id,),
            ).fetchone()
        return _paper_row_to_payload(row) if row else None

    def list_report_papers(self, report_id: str) -> list[dict[str, Any]]:
        report = self.get_report(report_id)
        if not report:
            raise KeyError(report_id)

        ids = report.get("related_paper_ids") or []
        if not ids:
            return []

        placeholders = ",".join(["?"] * len(ids))
        with self.conn() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    p.id,
                    p.title,
                    p.authors,
                    p.published_at,
                    p.source,
                    p.online_url,
                    p.pdf_url,
                    p.abstract,
                    p.extra,
                    p.local_pdf_path,
                    p.local_text_path,
                    a.recommendation_records,
                    a.user_notes,
                    a.ai_report_summary,
                    a.ai_report_path,
                    a."like" AS activity_like
                FROM papers p
                LEFT JOIN activity a ON a.id = p.id
                WHERE p.id IN ({placeholders})
                """,
                ids,
            ).fetchall()

        payload_map: dict[str, dict[str, Any]] = {}
        for row in rows:
            payload = _paper_row_to_payload(row)
            payload_map[payload["id"]] = payload
        ordered: list[dict[str, Any]] = []
        for paper_id in ids:
            item = payload_map.get(paper_id)
            if item:
                ordered.append(item)
        return ordered

    def update_user_notes(self, paper_id: str, user_notes: str) -> dict[str, Any]:
        if not self.paper_exists(paper_id):
            raise KeyError(paper_id)

        with self.conn() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO activity (
                    id, recommendation_records, user_notes, ai_report_summary, ai_report_path, "like"
                ) VALUES (?, '[]', '', '', '', 0)
                """,
                (paper_id,),
            )
            conn.execute(
                "UPDATE activity SET user_notes = ? WHERE id = ?",
                (user_notes, paper_id),
            )
            row = conn.execute(
                """
                SELECT id, recommendation_records, user_notes, ai_report_summary, ai_report_path, "like" AS activity_like
                FROM activity
                WHERE id = ?
                """,
                (paper_id,),
            ).fetchone()

        if not row:
            raise RuntimeError(f"Failed to update notes for {paper_id}")

        return {
            "id": row["id"],
            "recommendation_records": _json_list(row["recommendation_records"]),
            "user_notes": row["user_notes"] or "",
            "ai_report_summary": row["ai_report_summary"] or "",
            "ai_report_path": row["ai_report_path"] or "",
            "like": _normalize_like(row["activity_like"]),
        }

    def update_like(self, paper_id: str, like: int) -> dict[str, Any]:
        if like not in {-1, 0, 1}:
            raise ValueError("like must be -1, 0, or 1")
        if not self.paper_exists(paper_id):
            raise KeyError(paper_id)

        with self.conn() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO activity (
                    id, recommendation_records, user_notes, ai_report_summary, ai_report_path, "like"
                ) VALUES (?, '[]', '', '', '', 0)
                """,
                (paper_id,),
            )
            conn.execute(
                'UPDATE activity SET "like" = ? WHERE id = ?',
                (like, paper_id),
            )
            row = conn.execute(
                """
                SELECT id, recommendation_records, user_notes, ai_report_summary, ai_report_path, "like" AS activity_like
                FROM activity
                WHERE id = ?
                """,
                (paper_id,),
            ).fetchone()

        if not row:
            raise RuntimeError(f"Failed to update like for {paper_id}")

        return {
            "id": row["id"],
            "recommendation_records": _json_list(row["recommendation_records"]),
            "user_notes": row["user_notes"] or "",
            "ai_report_summary": row["ai_report_summary"] or "",
            "ai_report_path": row["ai_report_path"] or "",
            "like": _normalize_like(row["activity_like"]),
        }


def _paper_row_to_payload(row: sqlite3.Row) -> dict[str, Any]:
    authors = _json_list(row["authors"])
    extra = _json_object(row["extra"])
    keywords = _extract_keywords(extra)

    recommendation_records = _json_list(row["recommendation_records"])

    return {
        "id": row["id"],
        "title": row["title"],
        "authors": authors,
        "keywords": keywords,
        "published_at": row["published_at"],
        "source": row["source"],
        "online_url": row["online_url"] or "",
        "pdf_url": row["pdf_url"] or "",
        "abstract": row["abstract"] or "",
        "extra": extra,
        "local_pdf_path": row["local_pdf_path"],
        "local_text_path": row["local_text_path"],
        "recommendation_records": recommendation_records,
        "user_notes": row["user_notes"] or "",
        "ai_report_summary": row["ai_report_summary"] or "",
        "ai_report_path": row["ai_report_path"] or "",
        "like": _normalize_like(row["activity_like"]),
    }


def _report_row_to_payload(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "report_date": row["report_date"],
        "generated_at": row["generated_at"],
        "related_paper_ids": _json_list(row["related_paper_ids"]),
        "local_md_path": row["local_md_path"] or "",
    }


def _extract_keywords(extra: dict[str, Any]) -> list[str]:
    candidates = [
        extra.get("keywords"),
        extra.get("key_words"),
        extra.get("categories"),
        extra.get("tags"),
    ]

    for raw in candidates:
        if isinstance(raw, list):
            values = [str(item).strip() for item in raw if str(item).strip()]
            if values:
                return values
        if isinstance(raw, str) and raw.strip():
            parts = [part.strip() for part in raw.replace(";", ",").split(",") if part.strip()]
            if parts:
                return parts

    return []


def _json_list(raw: Any) -> list[Any]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        if not raw.strip():
            return []
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return parsed
    return []


def _json_object(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        if not raw.strip():
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return parsed
    return {}


def _normalize_like(raw: Any) -> int:
    if raw is None:
        return 0
    if isinstance(raw, bool):
        return int(raw)
    if isinstance(raw, int) and raw in {-1, 0, 1}:
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = int(raw.strip())
        except ValueError:
            return 0
        if parsed in {-1, 0, 1}:
            return parsed
    return 0
