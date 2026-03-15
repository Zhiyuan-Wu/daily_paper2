"""SQLite repository for paper embeddings persisted with sqlite-vec."""

from __future__ import annotations

import json
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

try:
    import pysqlite3.dbapi2 as sqlite3
except ImportError:  # pragma: no cover - fallback for environments without pysqlite3
    import sqlite3

from models.paper import PaperMetadata
from models.paper_embedding import PaperEmbeddingRecord
from service.common.sqlite_utils import validate_table_name

_VECTOR_DIM_PATTERN = re.compile(r"embedding\s+float\[(\d+)\]")


class PaperEmbeddingRepository:
    """Persistence layer for embedding vectors."""

    def __init__(
        self,
        db_path: str | Path,
        embedding_table: str = "paper_embeddings",
    ) -> None:
        self.db_path = Path(db_path)
        self.embedding_table = validate_table_name(embedding_table)
        self.vector_table = validate_table_name(f"{self.embedding_table}_vec")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            self._load_sqlite_vec(conn)
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
            conn.execute("CREATE INDEX IF NOT EXISTS idx_papers_fetched_at ON papers(fetched_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_papers_published_at ON papers(published_at)")
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.embedding_table} (
                    paper_id TEXT PRIMARY KEY,
                    meta_text TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    fetched_at TEXT NOT NULL,
                    embedded_at TEXT NOT NULL,
                    embedding_model TEXT NOT NULL,
                    embedding_dim INTEGER NOT NULL,
                    FOREIGN KEY (paper_id) REFERENCES papers(id)
                )
                """
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.embedding_table}_fetched_at "
                f"ON {self.embedding_table}(fetched_at)"
            )

    @staticmethod
    def _load_sqlite_vec(conn: sqlite3.Connection) -> None:
        if not hasattr(conn, "enable_load_extension"):
            raise RuntimeError(
                "SQLite connection does not support loadable extensions. "
                "On macOS, install and use 'pysqlite3' in your virtualenv."
            )
        try:
            import sqlite_vec
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError(
                "Missing dependency 'sqlite-vec'. Install with: pip install sqlite-vec"
            ) from exc

        sqlite_vec.load(conn)

    @staticmethod
    def _serialize_vector(values: list[float]) -> bytes:
        try:
            import sqlite_vec
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError(
                "Missing dependency 'sqlite-vec'. Install with: pip install sqlite-vec"
            ) from exc
        return sqlite_vec.serialize_float32(values)

    @staticmethod
    def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
            (table_name,),
        ).fetchone()
        return row is not None

    def _get_vector_dim(self, conn: sqlite3.Connection) -> int | None:
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name = ?",
            (self.vector_table,),
        ).fetchone()
        if not row:
            return None
        sql = str((row["sql"] or "")).lower()
        matched = _VECTOR_DIM_PATTERN.search(sql)
        if not matched:
            return None
        return int(matched.group(1))

    def _ensure_vector_index(self, conn: sqlite3.Connection, dim: int) -> None:
        if dim <= 0:
            raise ValueError("embedding_dim must be greater than 0")

        current_dim = self._get_vector_dim(conn)
        if current_dim == dim:
            return

        if current_dim is not None:
            conn.execute(f"DROP TABLE {self.vector_table}")

        conn.execute(
            f"""
            CREATE VIRTUAL TABLE {self.vector_table}
            USING vec0(
                paper_id TEXT PRIMARY KEY,
                embedding FLOAT[{dim}] distance_metric=cosine
            )
            """
        )

    def get_max_papers_fetched_at(self) -> datetime | None:
        with self._conn() as conn:
            row = conn.execute("SELECT MAX(fetched_at) AS max_fetched_at FROM papers").fetchone()
            if not row:
                return None
            value = row["max_fetched_at"]
            if not value:
                return None
            return _from_iso(value)

    def list_papers_for_embedding(self) -> list[PaperMetadata]:
        with self._conn() as conn:
            rows = conn.execute(
                f"""
                SELECT p.*
                FROM papers p
                LEFT JOIN {self.embedding_table} e ON e.paper_id = p.id
                WHERE p.fetched_at IS NOT NULL AND e.paper_id IS NULL
                ORDER BY p.fetched_at ASC, p.id ASC
                """
            ).fetchall()
            return [self._row_to_metadata(row) for row in rows]

    def upsert_embeddings(self, records: list[PaperEmbeddingRecord]) -> None:
        if not records:
            return

        dims = {record.embedding_dim for record in records}
        if len(dims) != 1:
            raise ValueError("Batch embeddings must share the same embedding_dim")
        dim = next(iter(dims))

        with self._conn() as conn:
            self._ensure_vector_index(conn, dim)
            for item in records:
                serialized = self._serialize_vector(item.embedding)
                conn.execute(
                    f"""
                    INSERT INTO {self.embedding_table} (
                        paper_id, meta_text, embedding, fetched_at, embedded_at,
                        embedding_model, embedding_dim
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(paper_id) DO UPDATE SET
                        meta_text=excluded.meta_text,
                        embedding=excluded.embedding,
                        fetched_at=excluded.fetched_at,
                        embedded_at=excluded.embedded_at,
                        embedding_model=excluded.embedding_model,
                        embedding_dim=excluded.embedding_dim
                    """,
                    (
                        item.paper_id,
                        item.meta_text,
                        serialized,
                        item.fetched_at.isoformat(),
                        item.embedded_at.isoformat(),
                        item.embedding_model,
                        item.embedding_dim,
                    ),
                )
                updated = conn.execute(
                    f"UPDATE {self.vector_table} SET embedding = ? WHERE paper_id = ?",
                    (serialized, item.paper_id),
                )
                if updated.rowcount == 0:
                    conn.execute(
                        f"INSERT INTO {self.vector_table} (paper_id, embedding) VALUES (?, ?)",
                        (item.paper_id, serialized),
                    )

    def count_embeddings(self) -> int:
        with self._conn() as conn:
            row = conn.execute(f"SELECT COUNT(*) AS c FROM {self.embedding_table}").fetchone()
            return int((row or {"c": 0})["c"])

    def clear_embeddings(self) -> None:
        with self._conn() as conn:
            conn.execute(f"DELETE FROM {self.embedding_table}")
            if self._table_exists(conn, self.vector_table):
                conn.execute(f"DELETE FROM {self.vector_table}")

    def search(
        self,
        query_embedding: list[float],
        top_k: int,
        *,
        published_from: datetime | None = None,
        published_to: datetime | None = None,
        fetched_from: datetime | None = None,
        fetched_to: datetime | None = None,
    ) -> list[tuple[PaperMetadata, float]]:
        if top_k <= 0:
            raise ValueError("top_k must be greater than 0")

        with self._conn() as conn:
            if not self._table_exists(conn, self.vector_table):
                rows = self._search_full_scan(
                    conn,
                    query_embedding,
                    top_k,
                    published_from=published_from,
                    published_to=published_to,
                    fetched_from=fetched_from,
                    fetched_to=fetched_to,
                )
            else:
                rows = self._search_with_vector_index(
                    conn,
                    query_embedding,
                    top_k,
                    published_from=published_from,
                    published_to=published_to,
                    fetched_from=fetched_from,
                    fetched_to=fetched_to,
                )

        output: list[tuple[PaperMetadata, float]] = []
        for row in rows:
            if row["distance"] is None:
                continue
            metadata = self._row_to_metadata(row)
            output.append((metadata, float(row["distance"])))
        return output

    def _search_with_vector_index(
        self,
        conn: sqlite3.Connection,
        query_embedding: list[float],
        top_k: int,
        *,
        published_from: datetime | None = None,
        published_to: datetime | None = None,
        fetched_from: datetime | None = None,
        fetched_to: datetime | None = None,
    ) -> list[sqlite3.Row]:
        total_row = conn.execute(
            f"SELECT COUNT(*) AS c FROM {self.vector_table}"
        ).fetchone()
        total_candidates = int((total_row or {"c": 0})["c"])
        if total_candidates <= 0:
            return []

        query_blob = self._serialize_vector(query_embedding)
        where: list[str] = ["e.embedding_dim = ?"]
        where_params: list[object] = [len(query_embedding)]

        if published_from is not None:
            where.append("p.published_at >= ?")
            where_params.append(published_from.isoformat())
        if published_to is not None:
            where.append("p.published_at <= ?")
            where_params.append(published_to.isoformat())
        if fetched_from is not None:
            where.append("p.fetched_at >= ?")
            where_params.append(fetched_from.isoformat())
        if fetched_to is not None:
            where.append("p.fetched_at <= ?")
            where_params.append(fetched_to.isoformat())

        where_sql = "WHERE " + " AND ".join(where)
        has_time_filters = any(value is not None for value in [published_from, published_to, fetched_from, fetched_to])

        k = min(total_candidates, max(top_k * (12 if has_time_filters else 8), top_k))
        while True:
            params: list[object] = [query_blob, k, *where_params, top_k]
            rows = conn.execute(
                f"""
                SELECT p.*, idx.distance AS distance
                FROM (
                    SELECT paper_id, distance
                    FROM {self.vector_table}
                    WHERE embedding MATCH ? AND k = ?
                ) idx
                JOIN {self.embedding_table} e ON e.paper_id = idx.paper_id
                JOIN papers p ON p.id = idx.paper_id
                {where_sql}
                ORDER BY idx.distance ASC
                LIMIT ?
                """,
                params,
            ).fetchall()
            if len(rows) >= top_k or k >= total_candidates:
                return rows
            next_k = min(total_candidates, k * 2)
            if next_k == k:
                return rows
            k = next_k

    def _search_full_scan(
        self,
        conn: sqlite3.Connection,
        query_embedding: list[float],
        top_k: int,
        *,
        published_from: datetime | None = None,
        published_to: datetime | None = None,
        fetched_from: datetime | None = None,
        fetched_to: datetime | None = None,
    ) -> list[sqlite3.Row]:
        params: list[object] = [self._serialize_vector(query_embedding)]
        where: list[str] = ["e.embedding_dim = ?"]
        params.append(len(query_embedding))
        if published_from is not None:
            where.append("p.published_at >= ?")
            params.append(published_from.isoformat())
        if published_to is not None:
            where.append("p.published_at <= ?")
            params.append(published_to.isoformat())
        if fetched_from is not None:
            where.append("p.fetched_at >= ?")
            params.append(fetched_from.isoformat())
        if fetched_to is not None:
            where.append("p.fetched_at <= ?")
            params.append(fetched_to.isoformat())

        where_sql = ""
        if where:
            where_sql = "WHERE " + " AND ".join(where)

        params.append(top_k)
        return conn.execute(
            f"""
            SELECT p.*, vec_distance_cosine(e.embedding, ?) AS distance
            FROM {self.embedding_table} e
            JOIN papers p ON p.id = e.paper_id
            {where_sql}
            ORDER BY distance ASC
            LIMIT ?
            """,
            params,
        ).fetchall()

    @staticmethod
    def _row_to_metadata(row: sqlite3.Row) -> PaperMetadata:
        data = dict(row)
        data["authors"] = json.loads(data.get("authors") or "[]")
        data["extra"] = json.loads(data.get("extra") or "{}")
        return PaperMetadata.from_db_row(data)


def _from_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
