from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from models.paper import PaperMetadata
from models.paper_embedding import PaperSearchHit
from service.activity_management.activity_manager import PaperActivityManager
from service.fetch.repository import PaperRepository
from service.recommand import PaperRecommandService

ROOT = Path(__file__).resolve().parents[1]


class _FakeEmbeddingService:
    def __init__(self, hits: list[PaperSearchHit]) -> None:
        self.hits = hits

    def search(self, query: str, *, top_k: int) -> list[PaperSearchHit]:
        if not query.strip():
            return []
        return self.hits[:top_k]


class _DummyPlugin:
    def __init__(self, name: str, scores: dict[str, float]) -> None:
        self.name = name
        self._scores = scores

    def recommend(self, request: object) -> dict[str, float]:
        return dict(self._scores)


def _seed_papers(db_path: Path, now: datetime | None = None) -> list[PaperMetadata]:
    current = now or datetime.now(timezone.utc)
    papers = [
        PaperMetadata(
            id="dummy:1",
            source="dummy",
            source_id="1",
            title="LLM retrieval systems",
            authors=["Alice"],
            abstract="retrieval and llm",
            fetched_at=current - timedelta(days=1),
            published_at=current - timedelta(days=2),
            online_url="https://example.org/1",
        ),
        PaperMetadata(
            id="dummy:2",
            source="dummy",
            source_id="2",
            title="Vision transformers",
            authors=["Bob"],
            abstract="vision model",
            fetched_at=current - timedelta(days=20),
            published_at=current - timedelta(days=21),
            online_url="https://example.org/2",
        ),
        PaperMetadata(
            id="dummy:3",
            source="dummy",
            source_id="3",
            title="Old paper",
            authors=["Carol"],
            abstract="old archive",
            fetched_at=current - timedelta(days=50),
            published_at=current - timedelta(days=55),
            online_url="https://example.org/3",
        ),
    ]
    PaperRepository(db_path).upsert_papers(papers)
    return papers


def test_semantic_plugin_recommend_scores(tmp_path: Path) -> None:
    db_path = tmp_path / "papers.db"
    papers = _seed_papers(db_path)

    fake_hits = [
        PaperSearchHit(paper=papers[0], distance=0.1),
        PaperSearchHit(paper=papers[1], distance=0.6),
    ]

    service = PaperRecommandService(
        db_path=db_path,
        semantic_embedding_service=_FakeEmbeddingService(fake_hits),
    )

    rows = service.recommend(algorithm="semantic", query="llm", top_k=2)
    assert len(rows) == 2
    assert rows[0].paper.id == "dummy:1"
    assert rows[0].score > rows[1].score
    assert 0 < rows[0].score <= 1


def test_interaction_plugin_score_rules(tmp_path: Path) -> None:
    db_path = tmp_path / "papers.db"
    _seed_papers(db_path)

    activity = PaperActivityManager(db_path=db_path)
    activity.create_activity(
        "dummy:1",
        recommendation_records=["2026-03-10T10:00:00Z"],
        user_notes="important",
        like=1,
    )
    activity.create_activity(
        "dummy:2",
        recommendation_records=["r1", "r2", "r3", "r4", "r5"],
        user_notes="",
        like=1,
    )
    activity.create_activity(
        "dummy:3",
        recommendation_records=["r1", "r2", "r3", "r4", "r5", "r6", "r7", "r8"],
        user_notes="",
        like=-1,
    )

    service = PaperRecommandService(db_path=db_path)
    rows = service.recommend(algorithm="interaction", top_k=5)
    ids = [row.paper.id for row in rows]

    assert ids[0] == "dummy:1"
    assert "dummy:2" in ids
    assert "dummy:3" not in ids


def test_time_plugin_decay(tmp_path: Path) -> None:
    db_path = tmp_path / "papers.db"
    now = datetime(2026, 3, 12, 12, 0, 0, tzinfo=timezone.utc)
    _seed_papers(db_path, now=now)

    service = PaperRecommandService(db_path=db_path)
    rows = service.recommend(algorithm="time", top_k=5, now=now.isoformat())
    ids = [row.paper.id for row in rows]

    assert "dummy:1" in ids
    assert "dummy:3" not in ids


def test_fusion_averages_with_missing_scores(tmp_path: Path) -> None:
    db_path = tmp_path / "papers.db"
    _seed_papers(db_path)

    service = PaperRecommandService(db_path=db_path)
    service.plugins = {}
    service.register_plugin(_DummyPlugin("a", {"dummy:1": 0.9, "dummy:2": 0.6}))
    service.register_plugin(_DummyPlugin("b", {"dummy:1": 0.3, "dummy:3": 0.9}))

    rows = service.recommend(algorithm="fusion", top_k=3)
    by_id = {row.paper.id: row for row in rows}

    assert by_id["dummy:1"].score == 0.6
    assert by_id["dummy:2"].score == 0.3
    assert by_id["dummy:3"].score == 0.45
    assert by_id["dummy:1"].algorithm_scores["a"] == 0.9
    assert by_id["dummy:1"].algorithm_scores["b"] == 0.3
    assert by_id["dummy:1"].algorithm_scores["fusion"] == 0.6


def test_fusion_uses_configurable_weights_with_normalization(tmp_path: Path) -> None:
    db_path = tmp_path / "papers.db"
    _seed_papers(db_path)

    service = PaperRecommandService(db_path=db_path)
    service.plugins = {}
    service.fusion_weights = {}
    service.register_plugin(_DummyPlugin("a", {"dummy:1": 1.0}), fusion_weight=3.0)
    service.register_plugin(_DummyPlugin("b", {"dummy:1": 0.0}), fusion_weight=0.0)

    rows = service.recommend(algorithm="fusion", top_k=1)
    assert len(rows) == 1

    # normalized weights: a=1.0, b=0.0
    assert rows[0].paper.id == "dummy:1"
    assert rows[0].score == 1.0


def test_cli_recommend_and_db_state(tmp_path: Path) -> None:
    db_path = tmp_path / "papers.db"
    _seed_papers(db_path, now=datetime(2026, 3, 12, 0, 0, 0, tzinfo=timezone.utc))

    cmd = [
        sys.executable,
        str(ROOT / "scripts/paper_recommand_cli.py"),
        "--db-path",
        str(db_path),
        "recommend",
        "--algorithm",
        "time",
        "--top-k",
        "2",
        "--now",
        "2026-03-12T00:00:00+00:00",
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True, cwd=str(ROOT))
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(proc.stdout)
    assert payload["algorithm"] == "time"
    assert payload["count"] >= 1
    assert len(payload["results"]) <= 2

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT COUNT(*) FROM papers").fetchone()
        assert row is not None
        assert row[0] == 3
    finally:
        conn.close()


def test_invalid_table_name_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        PaperRecommandService(
            db_path=tmp_path / "papers.db",
            paper_table='papers;DROP TABLE activity;',
        )
