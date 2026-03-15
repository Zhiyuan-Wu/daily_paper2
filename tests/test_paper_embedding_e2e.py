from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

pytest.importorskip("sqlite_vec")

from service.embedding import PaperEmbeddingService
from service.fetch.paper_fetch import PaperFetch


def _ensure_ollama_embedding_available(service: PaperEmbeddingService) -> None:
    try:
        vector = service.embed_text("health check for embedding service")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Ollama embedding endpoint/model not available: {exc}")
    if not vector:
        pytest.skip("Ollama returned empty embedding vector")


@pytest.mark.e2e
def test_e2e_embedding_sync_search_and_db_state(tmp_path: Path) -> None:
    db_path = tmp_path / "papers.db"
    papers_dir = tmp_path / "papers"
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=30)

    fetch = PaperFetch(
        db_path=db_path,
        papers_dir=papers_dir,
        max_downloaded_papers=10,
    )

    papers = fetch.search_online(
        source="arxiv",
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        limit=1,
    )
    if not papers:
        pytest.skip("arXiv returned no papers for embedding e2e query")

    downloaded = fetch.download_paper(papers[0].id)
    assert downloaded.local_pdf_path is not None
    local_pdf = Path(downloaded.local_pdf_path)
    assert local_pdf.exists()
    assert local_pdf.stat().st_size > 1024

    embedding_service = PaperEmbeddingService(db_path=db_path)
    _ensure_ollama_embedding_available(embedding_service)

    result = embedding_service.sync_incremental()
    assert result.processed_paper_count >= 1

    query_text = " ".join(downloaded.title.split()[:8])
    hits = embedding_service.search(
        query_text,
        top_k=1,
        fetched_from=start_date.isoformat(),
        fetched_to=end_date.isoformat(),
    )
    assert hits
    assert any(hit.paper.id == downloaded.id for hit in hits)

    conn = sqlite3.connect(db_path)
    try:
        embedding_row = conn.execute(
            "SELECT meta_text, embedding_dim FROM paper_embeddings WHERE paper_id = ?",
            (downloaded.id,),
        ).fetchone()
        assert embedding_row is not None
        assert len(embedding_row[0]) > 20
        assert int(embedding_row[1]) > 0

        paper_row = conn.execute(
            "SELECT local_pdf_path FROM papers WHERE id = ?",
            (downloaded.id,),
        ).fetchone()
        assert paper_row is not None
        assert paper_row[0] == str(local_pdf)
    finally:
        conn.close()
