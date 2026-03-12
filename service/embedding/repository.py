"""SQLite repository for paper embeddings persisted with sqlite-vec."""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

try:
    import pysqlite3.dbapi2 as sqlite3
except ImportError:  # pragma: no cover - fallback for environments without pysqlite3
    import sqlite3

from models.paper import PaperMetadata
from models.paper_embedding import PaperEmbeddingRecord, PaperEmbeddingVersion


class PaperEmbeddingRepository:
    """Persistence layer for embedding vectors and sync versions."""

    def __init__(
        self,
        db_path: str | Path,
        embedding_table: str = "paper_embeddings",
        version_table: str = "paper_embedding_versions",
    ) -> None:
        self.db_path = Path(db_path)
        self.embedding_table = embedding_table
        self.version_table = version_table
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
                f"""
                CREATE TABLE IF NOT EXISTS {self.version_table} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    synced_at TEXT NOT NULL,
                    max_fetched_at TEXT,
                    processed_paper_count INTEGER NOT NULL,
                    embedding_model TEXT NOT NULL,
                    embedding_dim INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.embedding_table}_fetched_at "
                f"ON {self.embedding_table}(fetched_at)"
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.version_table}_max_fetched_at "
                f"ON {self.version_table}(max_fetched_at)"
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

    def get_latest_version(self) -> PaperEmbeddingVersion | None:
        with self._conn() as conn:
            row = conn.execute(
                f"SELECT * FROM {self.version_table} ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if not row:
                return None
            return PaperEmbeddingVersion.from_db_row(dict(row))

    def get_max_papers_fetched_at(self) -> datetime | None:
        with self._conn() as conn:
            row = conn.execute("SELECT MAX(fetched_at) AS max_fetched_at FROM papers").fetchone()
            if not row:
                return None
            value = row["max_fetched_at"]
            if not value:
                return None
            return _from_iso(value)

    def list_papers_for_embedding(
        self,
        since_fetched_at: datetime | None = None,
        limit: int | None = None,
    ) -> list[PaperMetadata]:
        params: list[object] = []
        where = ["fetched_at IS NOT NULL"]
        if since_fetched_at is not None:
            where.append("fetched_at > ?")
            params.append(since_fetched_at.isoformat())

        sql = "SELECT * FROM papers"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY fetched_at ASC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)

        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [self._row_to_metadata(row) for row in rows]

    def upsert_embeddings(self, records: list[PaperEmbeddingRecord]) -> None:
        if not records:
            return

        with self._conn() as conn:
            for item in records:
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
                        self._serialize_vector(item.embedding),
                        item.fetched_at.isoformat(),
                        item.embedded_at.isoformat(),
                        item.embedding_model,
                        item.embedding_dim,
                    ),
                )

    def save_version(self, version: PaperEmbeddingVersion) -> PaperEmbeddingVersion:
        with self._conn() as conn:
            cursor = conn.execute(
                f"""
                INSERT INTO {self.version_table} (
                    synced_at, max_fetched_at, processed_paper_count,
                    embedding_model, embedding_dim
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    version.synced_at.isoformat(),
                    version.max_fetched_at.isoformat() if version.max_fetched_at else None,
                    version.processed_paper_count,
                    version.embedding_model,
                    version.embedding_dim,
                ),
            )
            version.id = int(cursor.lastrowid)
        return version

    def count_embeddings(self) -> int:
        with self._conn() as conn:
            row = conn.execute(f"SELECT COUNT(*) AS c FROM {self.embedding_table}").fetchone()
            return int((row or {"c": 0})["c"])

    def clear_embeddings(self) -> None:
        with self._conn() as conn:
            conn.execute(f"DELETE FROM {self.embedding_table}")

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
        with self._conn() as conn:
            rows = conn.execute(
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

        output: list[tuple[PaperMetadata, float]] = []
        for row in rows:
            if row["distance"] is None:
                continue
            metadata = self._row_to_metadata(row)
            output.append((metadata, float(row["distance"])))
        return output

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
