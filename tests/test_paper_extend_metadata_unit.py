from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from models.paper import PaperMetadata
from models.paper_extend_metadata import PaperExtendMetadataRecord
from service.extend_metadata import PaperExtendMetadataService
from service.fetch.repository import PaperRepository


class _DummyFetchService:
    def __init__(self, papers: dict[str, PaperMetadata]) -> None:
        self.papers = papers
        self.calls: list[tuple[str, bool]] = []

    def download_paper(self, paper_id: str, force_refresh: bool = False, **kwargs):  # type: ignore[override]
        self.calls.append((paper_id, force_refresh))
        return self.papers[paper_id]


class _DummyParser:
    def __init__(self, page_text: str) -> None:
        self.page_text = page_text
        self.calls: list[str] = []

    def parse_pdf_first_page(self, pdf_path: str | Path) -> str:
        self.calls.append(str(pdf_path))
        return self.page_text


class _DummyLLMClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def extract(self, *, paper: PaperMetadata, first_page_text: str) -> dict:
        self.calls.append((paper.id, first_page_text))
        return {
            "abstract_cn": "这是一篇中文摘要。",
            "affliations": ["Tsinghua University", "OpenAI", "OpenAI"],
            "keywords": "llm, agents, llm",
            "github_repo": "",
        }


def _insert_paper(db_path: Path, paper_id: str, pdf_path: Path) -> PaperMetadata:
    repo = PaperRepository(db_path)
    paper = PaperMetadata(
        id=paper_id,
        source="dummy",
        source_id=paper_id.split(":", 1)[1],
        title=f"Paper {paper_id}",
        authors=["Alice", "Bob"],
        abstract="This is the original abstract.",
        online_url="https://example.org/paper",
        local_pdf_path=str(pdf_path),
        fetched_at=datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc),
        published_at=datetime(2026, 2, 28, 12, 0, 0, tzinfo=timezone.utc),
    )
    repo.upsert_papers([paper])
    return paper


def test_get_extended_metadata_persists_record(tmp_path: Path) -> None:
    db_path = tmp_path / "papers.db"
    pdf_path = tmp_path / "dummy.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%dummy\n")

    paper = _insert_paper(db_path, "dummy:1", pdf_path)
    fetch_service = _DummyFetchService({paper.id: paper})
    parser = _DummyParser(
        "Affiliations: Tsinghua University; OpenAI\nCode: https://github.com/example/project"
    )
    llm_client = _DummyLLMClient()

    service = PaperExtendMetadataService(
        db_path=db_path,
        fetch_service=fetch_service,
        parser=parser,
        llm_client=llm_client,
    )

    payload = service.get_extended_metadata(paper.id)
    assert payload["paper_id"] == paper.id
    assert payload["abstract_cn"] == "这是一篇中文摘要。"
    assert payload["affliations"] == ["Tsinghua University", "OpenAI"]
    assert payload["keywords"] == ["llm", "agents"]
    assert payload["github_repo"] == "https://github.com/example/project"
    assert payload["extracted_at"]

    assert fetch_service.calls == [(paper.id, False)]
    assert len(parser.calls) == 1
    assert len(llm_client.calls) == 1

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT abstract_cn, affliations, keywords, github_repo FROM extend_metadata WHERE paper_id = ?",
            (paper.id,),
        ).fetchone()
        assert row is not None
        assert row[0] == "这是一篇中文摘要。"
        assert json.loads(row[1]) == ["Tsinghua University", "OpenAI"]
        assert json.loads(row[2]) == ["llm", "agents"]
        assert row[3] == "https://github.com/example/project"
    finally:
        conn.close()


def test_get_extended_metadata_uses_cache_by_default(tmp_path: Path) -> None:
    db_path = tmp_path / "papers.db"
    pdf_path = tmp_path / "cached.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%cached\n")

    paper = _insert_paper(db_path, "dummy:cached", pdf_path)
    fetch_service = _DummyFetchService({paper.id: paper})
    parser = _DummyParser("cached first page")
    llm_client = _DummyLLMClient()

    service = PaperExtendMetadataService(
        db_path=db_path,
        fetch_service=fetch_service,
        parser=parser,
        llm_client=llm_client,
    )

    first = service.get_extended_metadata(paper.id)
    second = service.get_extended_metadata(paper.id)
    assert first == second
    assert len(fetch_service.calls) == 1
    assert len(parser.calls) == 1
    assert len(llm_client.calls) == 1


def test_sync_incremental_only_processes_missing_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "papers.db"
    pdf_paths: dict[str, Path] = {}
    papers: dict[str, PaperMetadata] = {}
    for idx in [1, 2, 3]:
        pdf_path = tmp_path / f"{idx}.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n%dummy\n")
        paper = _insert_paper(db_path, f"dummy:{idx}", pdf_path)
        pdf_paths[paper.id] = pdf_path
        papers[paper.id] = paper

    service = PaperExtendMetadataService(
        db_path=db_path,
        fetch_service=_DummyFetchService(papers),
        parser=_DummyParser("first page with https://github.com/example/project"),
        llm_client=_DummyLLMClient(),
    )
    service.repo.upsert_record(
        PaperExtendMetadataRecord(
            paper_id="dummy:1",
            abstract_cn="已有数据",
            affliations=["Existing Lab"],
            keywords=["cached"],
            github_repo="https://github.com/existing/repo",
            extracted_at=datetime(2026, 3, 2, 12, 0, 0, tzinfo=timezone.utc),
        )
    )

    result = service.sync_incremental()
    assert result.processed_paper_count == 2
    assert result.failed_paper_count == 0
    assert service.repo.count_records() == 3

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT paper_id FROM extend_metadata ORDER BY paper_id ASC").fetchall()
        assert [row[0] for row in rows] == ["dummy:1", "dummy:2", "dummy:3"]
    finally:
        conn.close()
