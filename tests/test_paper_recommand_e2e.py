from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from service.activity_management.activity_manager import PaperActivityManager
from service.fetch.paper_fetch import PaperFetch
from service.recommand import PaperRecommandService


@pytest.mark.e2e
def test_e2e_recommand_with_real_query_download_and_db_state(tmp_path: Path) -> None:
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
        keywords=["language model"],
        limit=3,
        category="cs.AI",
    )
    if not papers:
        pytest.skip("arXiv returned no papers for recommendation e2e query")

    downloaded = fetch.download_paper(papers[0].id)
    assert downloaded.local_pdf_path is not None
    local_pdf = Path(downloaded.local_pdf_path)
    assert local_pdf.exists()
    assert local_pdf.stat().st_size > 1024

    activity_manager = PaperActivityManager(db_path=db_path)
    activity_manager.create_activity(
        downloaded.id,
        recommendation_records=["2026-03-12T08:00:00Z", "2026-03-12T09:00:00Z"],
        user_notes="read carefully",
        like=1,
        overwrite=True,
    )

    service = PaperRecommandService(db_path=db_path)
    fusion_rows = service.recommend(algorithm="fusion", top_k=5)
    assert fusion_rows
    assert any(row.paper.id == downloaded.id for row in fusion_rows)

    time_rows = service.recommend(algorithm="time", top_k=5)
    assert time_rows

    conn = sqlite3.connect(db_path)
    try:
        paper_row = conn.execute(
            "SELECT local_pdf_path FROM papers WHERE id = ?",
            (downloaded.id,),
        ).fetchone()
        assert paper_row is not None
        assert paper_row[0] == str(local_pdf)

        activity_row = conn.execute(
            'SELECT user_notes, "like" FROM activity WHERE id = ?',
            (downloaded.id,),
        ).fetchone()
        assert activity_row is not None
        assert activity_row[0] == "read carefully"
        assert activity_row[1] == 1
    finally:
        conn.close()
