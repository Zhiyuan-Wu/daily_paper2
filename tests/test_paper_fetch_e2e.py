from __future__ import annotations

import socket
import sqlite3
from pathlib import Path

import pytest

from service.fetch.paper_fetch import PaperFetch


def _proxy_available(host: str = "127.0.0.1", port: int = 7890) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


@pytest.mark.e2e
def test_e2e_arxiv_query_download_and_db_state(tmp_path: Path) -> None:
    fetch = PaperFetch(
        db_path=tmp_path / "papers.db",
        papers_dir=tmp_path / "papers",
        max_downloaded_papers=3,
    )

    papers = fetch.search_online(
        source="arxiv",
        start_date="2026-03-01",
        end_date="2026-03-08",
        keywords=["llm"],
        limit=3,
        category="cs.AI",
    )
    if not papers:
        pytest.skip("arXiv returned no papers for the selected date range/keywords")

    downloaded = fetch.download_paper(papers[0].id)
    assert downloaded.local_pdf_path is not None
    local_path = Path(downloaded.local_pdf_path)
    assert local_path.exists()
    assert local_path.stat().st_size > 1024

    conn = sqlite3.connect(tmp_path / "papers.db")
    try:
        row = conn.execute(
            "SELECT local_pdf_path FROM papers WHERE id = ?",
            (downloaded.id,),
        ).fetchone()
        assert row is not None
        assert row[0] == str(local_path)
    finally:
        conn.close()


@pytest.mark.e2e
def test_e2e_huggingface_query_download_and_db_state(tmp_path: Path) -> None:
    if not _proxy_available():
        pytest.skip("localhost:7890 proxy not available for HuggingFace source")

    fetch = PaperFetch(
        db_path=tmp_path / "papers.db",
        papers_dir=tmp_path / "papers",
        max_downloaded_papers=3,
    )

    papers = fetch.search_online(
        source="huggingface",
        start_date="2026-03-06",
        end_date="2026-03-06",
        keywords=["language"],
        limit=5,
    )
    if not papers:
        pytest.skip("HuggingFace returned no papers for the selected date range/keywords")
    assert all(p.source == "huggingface" for p in papers)

    downloaded = fetch.download_paper(papers[0].id)
    assert downloaded.local_pdf_path is not None
    local_path = Path(downloaded.local_pdf_path)
    assert local_path.exists()
    assert local_path.stat().st_size > 1024

    conn = sqlite3.connect(tmp_path / "papers.db")
    try:
        row = conn.execute(
            "SELECT local_pdf_path FROM papers WHERE id = ?",
            (downloaded.id,),
        ).fetchone()
        assert row is not None
        assert row[0] == str(local_path)
    finally:
        conn.close()
