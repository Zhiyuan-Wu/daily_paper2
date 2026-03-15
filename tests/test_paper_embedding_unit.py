from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread

import pytest

pytest.importorskip("sqlite_vec")

from models.paper import PaperMetadata
from service.embedding.embedding_service import PaperEmbeddingService
from service.fetch.repository import PaperRepository

ROOT = Path(__file__).resolve().parents[1]


class _FakeEmbedHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        payload = json.loads(raw.decode("utf-8"))

        input_value = payload.get("input")
        if isinstance(input_value, str):
            texts = [input_value]
        else:
            texts = list(input_value or [])

        vectors = [_text_to_vector(text) for text in texts]
        body = {"model": payload.get("model"), "embeddings": vectors}

        encoded = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return None


@pytest.fixture
def fake_embed_endpoint() -> str:
    server = HTTPServer(("127.0.0.1", 0), _FakeEmbedHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}/api/embed"
    finally:
        server.shutdown()
        thread.join(timeout=2)


def _insert_sample_papers(db_path: Path) -> None:
    repo = PaperRepository(db_path)
    papers = [
        PaperMetadata(
            id="dummy:1",
            source="dummy",
            source_id="1",
            title="LLM reasoning with retrieval",
            authors=["Alice"],
            abstract="A large language model paper focused on retrieval augmented generation.",
            online_url="https://example.org/1",
            fetched_at=datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc),
            published_at=datetime(2026, 2, 28, 10, 0, 0, tzinfo=timezone.utc),
            extra={"keywords": ["llm", "retrieval", "rag"]},
        ),
        PaperMetadata(
            id="dummy:2",
            source="dummy",
            source_id="2",
            title="Vision transformer for image recognition",
            authors=["Bob"],
            abstract="An image recognition paper about computer vision models.",
            online_url="https://example.org/2",
            fetched_at=datetime(2026, 3, 2, 10, 0, 0, tzinfo=timezone.utc),
            published_at=datetime(2026, 2, 27, 10, 0, 0, tzinfo=timezone.utc),
            extra={"keywords": ["vision", "image", "transformer"]},
        ),
    ]
    repo.upsert_papers(papers)


def _text_to_vector(text: str) -> list[float]:
    lowered = text.lower()
    llm = lowered.count("llm") + lowered.count("language model")
    vision = lowered.count("vision") + lowered.count("image")
    retrieval = lowered.count("retrieval") + lowered.count("search")
    size = max(len(lowered), 1) / 100.0
    return [float(llm), float(vision), float(retrieval), float(size)]


def test_sync_incremental_and_semantic_search(tmp_path: Path, fake_embed_endpoint: str) -> None:
    db_path = tmp_path / "papers.db"
    _insert_sample_papers(db_path)

    service = PaperEmbeddingService(
        db_path=db_path,
        ollama_endpoint=fake_embed_endpoint,
        ollama_model="fake-embed",
        default_batch_size=2,
    )

    result = service.sync_incremental()
    assert result.processed_paper_count == 2
    assert result.embedding_model == "fake-embed"
    assert service.repo.count_embeddings() == 2

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
            ("paper_embeddings_vec",),
        ).fetchone()
        assert row is not None
    finally:
        conn.close()

    hits = service.search("llm retrieval", top_k=2)
    assert len(hits) == 2
    assert hits[0].paper.id == "dummy:1"
    assert hits[0].distance <= hits[1].distance


def test_incremental_sync_only_processes_new_rows(tmp_path: Path, fake_embed_endpoint: str) -> None:
    db_path = tmp_path / "papers.db"
    _insert_sample_papers(db_path)

    service = PaperEmbeddingService(
        db_path=db_path,
        ollama_endpoint=fake_embed_endpoint,
        ollama_model="fake-embed",
        default_batch_size=2,
    )

    first = service.sync_incremental()
    assert first.processed_paper_count == 2

    repo = PaperRepository(db_path)
    repo.upsert_papers(
        [
            PaperMetadata(
                id="dummy:3",
                source="dummy",
                source_id="3",
                title="Search systems for agents",
                authors=["Carol"],
                abstract="A retrieval and search systems paper.",
                online_url="https://example.org/3",
                fetched_at=datetime(2026, 3, 3, 10, 0, 0, tzinfo=timezone.utc),
                published_at=datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc),
                extra={"keywords": ["retrieval", "search", "agent"]},
            )
        ]
    )

    second = service.sync_incremental()
    assert second.processed_paper_count == 1
    assert service.repo.count_embeddings() == 3


def test_incremental_sync_picks_late_backfill_without_force_full(
    tmp_path: Path, fake_embed_endpoint: str
) -> None:
    db_path = tmp_path / "papers.db"
    _insert_sample_papers(db_path)

    service = PaperEmbeddingService(
        db_path=db_path,
        ollama_endpoint=fake_embed_endpoint,
        ollama_model="fake-embed",
        default_batch_size=2,
    )

    first = service.sync_incremental()
    assert first.processed_paper_count == 2

    repo = PaperRepository(db_path)
    repo.upsert_papers(
        [
            PaperMetadata(
                id="dummy:late",
                source="dummy",
                source_id="late",
                title="Late backfilled paper",
                authors=["Late Author"],
                abstract="old timestamp but newly inserted",
                online_url="https://example.org/late",
                fetched_at=datetime(2026, 2, 1, 10, 0, 0, tzinfo=timezone.utc),
                published_at=datetime(2026, 2, 1, 10, 0, 0, tzinfo=timezone.utc),
                extra={"keywords": ["late"]},
            )
        ]
    )

    second = service.sync_incremental()
    assert second.processed_paper_count == 1
    assert service.repo.count_embeddings() == 3


def test_incremental_sync_indexes_all_missing_embeddings(tmp_path: Path, fake_embed_endpoint: str) -> None:
    db_path = tmp_path / "papers.db"
    repo = PaperRepository(db_path)
    same_ts = datetime(2026, 3, 2, 10, 0, 0, tzinfo=timezone.utc)
    repo.upsert_papers(
        [
            PaperMetadata(
                id=f"dummy:{idx}",
                source="dummy",
                source_id=str(idx),
                title=f"Paper {idx}",
                authors=["Author"],
                abstract="same fetched_at batch",
                online_url=f"https://example.org/{idx}",
                fetched_at=same_ts,
                published_at=same_ts,
                extra={"keywords": ["batch"]},
            )
            for idx in [1, 2, 3]
        ]
    )

    service = PaperEmbeddingService(
        db_path=db_path,
        ollama_endpoint=fake_embed_endpoint,
        ollama_model="fake-embed",
        default_batch_size=2,
    )

    result = service.sync_incremental()
    assert result.processed_paper_count == 3
    assert service.repo.count_embeddings() == 3


def test_search_supports_time_filter(tmp_path: Path, fake_embed_endpoint: str) -> None:
    db_path = tmp_path / "papers.db"
    _insert_sample_papers(db_path)

    service = PaperEmbeddingService(
        db_path=db_path,
        ollama_endpoint=fake_embed_endpoint,
        ollama_model="fake-embed",
    )
    service.sync_incremental()

    hits = service.search("vision", top_k=5, fetched_from="2026-03-02", fetched_to="2026-03-02")
    assert len(hits) == 1
    assert hits[0].paper.id == "dummy:2"


def test_embed_texts_supports_batch(tmp_path: Path, fake_embed_endpoint: str) -> None:
    service = PaperEmbeddingService(
        db_path=tmp_path / "papers.db",
        ollama_endpoint=fake_embed_endpoint,
        ollama_model="fake-embed",
    )

    vectors = service.embed_texts(["hello", "llm retrieval"], batch_size=2)
    assert len(vectors) == 2
    assert all(len(vec) == 4 for vec in vectors)


def test_cli_sync_and_search(tmp_path: Path, fake_embed_endpoint: str) -> None:
    db_path = tmp_path / "papers.db"
    _insert_sample_papers(db_path)

    sync_cmd = [
        sys.executable,
        str(ROOT / "scripts/paper_embedding_cli.py"),
        "--db-path",
        str(db_path),
        "--endpoint",
        fake_embed_endpoint,
        "--model",
        "fake-embed-cli",
        "--batch-size",
        "2",
        "sync",
    ]
    sync_proc = subprocess.run(sync_cmd, check=False, capture_output=True, text=True, cwd=str(ROOT))
    assert sync_proc.returncode == 0, sync_proc.stderr
    sync_payload = json.loads(sync_proc.stdout)
    assert sync_payload["processed_paper_count"] == 2
    assert "synced_at" in sync_payload

    search_cmd = [
        sys.executable,
        str(ROOT / "scripts/paper_embedding_cli.py"),
        "--db-path",
        str(db_path),
        "--endpoint",
        fake_embed_endpoint,
        "--model",
        "fake-embed-cli",
        "search",
        "llm",
        "--top-k",
        "1",
    ]
    search_proc = subprocess.run(search_cmd, check=False, capture_output=True, text=True, cwd=str(ROOT))
    assert search_proc.returncode == 0, search_proc.stderr
    search_payload = json.loads(search_proc.stdout)
    assert search_payload["count"] == 1
    assert search_payload["hits"][0]["paper"]["id"] == "dummy:1"

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT COUNT(*) FROM paper_embeddings").fetchone()
        assert row is not None
        assert row[0] == 2
    finally:
        conn.close()


def test_invalid_embedding_table_name_rejected(tmp_path: Path, fake_embed_endpoint: str) -> None:
    with pytest.raises(ValueError):
        PaperEmbeddingService(
            db_path=tmp_path / "papers.db",
            embedding_table='paper_embeddings;DROP TABLE papers;',
            ollama_endpoint=fake_embed_endpoint,
            ollama_model="fake-embed",
        )
