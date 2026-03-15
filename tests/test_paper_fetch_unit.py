from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from models.paper import PaperMetadata
from service.fetch.paper_fetch import PaperFetch
from service.fetch.sources.base import PaperSource


class DummySource(PaperSource):
    name = "dummy"

    def __init__(self) -> None:
        self._items: dict[str, PaperMetadata] = {}
        self.download_calls = 0

    def search(self, **kwargs):  # type: ignore[override]
        return list(self._items.values())

    def fetch_by_id(self, source_id: str, **kwargs):  # type: ignore[override]
        return self._items.get(source_id)

    def download(self, paper: PaperMetadata, target_dir: Path, **kwargs):  # type: ignore[override]
        self.download_calls += 1
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{paper.id.replace(':', '_')}.pdf"
        target.write_bytes(b"%PDF-1.4\n%dummy\n")
        return target


def test_search_online_persists_metadata(tmp_path: Path) -> None:
    fetch = PaperFetch(
        db_path=tmp_path / "papers.db",
        papers_dir=tmp_path / "papers",
        max_downloaded_papers=10,
    )

    dummy = DummySource()
    fetch.register_source(dummy)

    paper = PaperMetadata(
        id="dummy:1",
        source="dummy",
        source_id="1",
        title="A Test Paper",
        authors=["Alice", "Bob"],
        published_at=datetime(2026, 3, 1, 10, 0, 0),
        abstract="this paper is about retrieval and testability",
        online_url="https://example.org/paper/1",
    )
    dummy._items["1"] = paper

    results = fetch.search_online(source="dummy", keywords=["retrieval"], limit=5)
    assert results
    assert results[0].id == "dummy:1"
    persisted = fetch.repo.get_by_id("dummy:1")
    assert persisted is not None
    assert persisted.title == "A Test Paper"


def test_lru_cleanup_by_download_count(tmp_path: Path) -> None:
    fetch = PaperFetch(
        db_path=tmp_path / "papers.db",
        papers_dir=tmp_path / "papers",
        max_downloaded_papers=1,
    )

    dummy = DummySource()
    fetch.register_source(dummy)

    for idx in ["1", "2"]:
        paper = PaperMetadata(
            id=f"dummy:{idx}",
            source="dummy",
            source_id=idx,
            title=f"Paper {idx}",
            authors=["Author"],
            published_at=datetime(2026, 3, 1, 10, 0, 0),
            abstract="",
            online_url=f"https://example.org/paper/{idx}",
        )
        dummy._items[idx] = paper
        fetch.search_online(source="dummy", limit=10)

    p1 = fetch.download_paper("dummy:1")
    assert p1.local_pdf_path is not None
    assert Path(p1.local_pdf_path).exists()

    p2 = fetch.download_paper("dummy:2")
    assert p2.local_pdf_path is not None
    assert Path(p2.local_pdf_path).exists()

    refreshed_p1 = fetch.repo.get_by_id("dummy:1")
    assert refreshed_p1 is not None
    assert refreshed_p1.local_pdf_path is None


def test_download_prefers_local_cache_unless_force_refresh(tmp_path: Path) -> None:
    fetch = PaperFetch(
        db_path=tmp_path / "papers.db",
        papers_dir=tmp_path / "papers",
        max_downloaded_papers=10,
    )

    dummy = DummySource()
    fetch.register_source(dummy)

    paper = PaperMetadata(
        id="dummy:cache-1",
        source="dummy",
        source_id="cache-1",
        title="Cache Test Paper",
        authors=["Alice"],
        published_at=datetime(2026, 3, 1, 10, 0, 0),
        abstract="cache test",
        online_url="https://example.org/paper/cache-1",
    )
    dummy._items["cache-1"] = paper
    fetch.search_online(source="dummy", limit=1)

    first = fetch.download_paper("dummy:cache-1")
    assert first.local_pdf_path is not None
    assert dummy.download_calls == 1

    second = fetch.download_paper("dummy:cache-1")
    assert second.local_pdf_path == first.local_pdf_path
    assert dummy.download_calls == 1

    third = fetch.download_paper("dummy:cache-1", force_refresh=True)
    assert third.local_pdf_path == first.local_pdf_path
    assert dummy.download_calls == 2


def test_search_online_does_not_overwrite_existing_rows(tmp_path: Path) -> None:
    fetch = PaperFetch(
        db_path=tmp_path / "papers.db",
        papers_dir=tmp_path / "papers",
        max_downloaded_papers=10,
    )

    dummy = DummySource()
    fetch.register_source(dummy)

    original = PaperMetadata(
        id="dummy:stable-1",
        source="dummy",
        source_id="stable-1",
        title="Original Title",
        authors=["Alice"],
        published_at=datetime(2026, 3, 1, 10, 0, 0),
        abstract="original abstract",
        online_url="https://example.org/paper/stable-1",
    )
    dummy._items["stable-1"] = original
    fetch.search_online(source="dummy", limit=5)

    downloaded = fetch.download_paper("dummy:stable-1")
    assert downloaded.local_pdf_path is not None

    changed_online = PaperMetadata(
        id="dummy:stable-1",
        source="dummy",
        source_id="stable-1",
        title="Changed Online Title",
        authors=["Alice", "Bob"],
        published_at=datetime(2026, 3, 2, 10, 0, 0),
        abstract="changed abstract",
        online_url="https://example.org/paper/stable-1-v2",
    )
    dummy._items["stable-1"] = changed_online
    fetch.search_online(source="dummy", limit=5)

    persisted = fetch.repo.get_by_id("dummy:stable-1")
    assert persisted is not None
    assert persisted.title == "Original Title"
    assert persisted.abstract == "original abstract"
    assert persisted.local_pdf_path == downloaded.local_pdf_path


def test_search_online_limit_must_be_positive(tmp_path: Path) -> None:
    fetch = PaperFetch(
        db_path=tmp_path / "papers.db",
        papers_dir=tmp_path / "papers",
        max_downloaded_papers=10,
    )
    dummy = DummySource()
    fetch.register_source(dummy)

    with pytest.raises(ValueError):
        fetch.search_online(source="dummy", limit=0)
