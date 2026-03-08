from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from models.paper_activity import PaperActivityRecord
from service.activity_management.activity_manager import PaperActivityManager


def test_model_roundtrip() -> None:
    record = PaperActivityRecord(
        id="arxiv:2603.05500",
        recommendation_records=["2026-03-08T12:00:00Z"],
        user_notes="read section 3",
        ai_report_summary="method summary",
        ai_report_path="data/reports/2603.05500.md",
    )
    row = record.to_db_row()
    restored = PaperActivityRecord.from_db_row(row)
    assert restored.id == record.id
    assert restored.recommendation_records == record.recommendation_records
    assert restored.user_notes == record.user_notes
    assert restored.ai_report_summary == record.ai_report_summary
    assert restored.ai_report_path == record.ai_report_path


def test_crud_and_raw_json_state(tmp_path: Path) -> None:
    manager = PaperActivityManager(db_path=tmp_path / "papers.db")
    paper_id = "arxiv:2603.05500"

    created = manager.create_activity(
        paper_id,
        recommendation_records=["2026-03-08T10:00:00Z"],
        user_notes="first note",
        ai_report_summary="summary v1",
        ai_report_path="data/reports/v1.md",
    )
    assert created.id == paper_id

    loaded = manager.get_activity(paper_id)
    assert loaded is not None
    assert loaded.recommendation_records == ["2026-03-08T10:00:00Z"]
    assert loaded.user_notes == "first note"

    updated = manager.update_activity(
        paper_id,
        recommendation_records=["2026-03-08T10:00:00Z", "2026-03-08T11:00:00Z"],
        user_notes="second note",
        ai_report_summary="summary v2",
        ai_report_path="data/reports/v2.md",
    )
    assert updated.user_notes == "second note"
    assert len(updated.recommendation_records) == 2

    conn = sqlite3.connect(tmp_path / "papers.db")
    try:
        row = conn.execute(
            "SELECT recommendation_records, user_notes, ai_report_summary, ai_report_path FROM activity WHERE id = ?",
            (paper_id,),
        ).fetchone()
        assert row is not None
        assert json.loads(row[0]) == ["2026-03-08T10:00:00Z", "2026-03-08T11:00:00Z"]
        assert row[1] == "second note"
        assert row[2] == "summary v2"
        assert row[3] == "data/reports/v2.md"
    finally:
        conn.close()

    deleted = manager.delete_activity(paper_id)
    assert deleted is True
    assert manager.get_activity(paper_id) is None


def test_append_recommendation_auto_create(tmp_path: Path) -> None:
    manager = PaperActivityManager(db_path=tmp_path / "papers.db")
    paper_id = "hf:paper-1"

    one = manager.append_recommendation(paper_id, "2026-03-08T08:00:00Z")
    assert one.recommendation_records == ["2026-03-08T08:00:00Z"]

    two = manager.append_recommendation(paper_id, "2026-03-08T09:00:00Z")
    assert two.recommendation_records == ["2026-03-08T08:00:00Z", "2026-03-08T09:00:00Z"]


def test_update_missing_record_raises(tmp_path: Path) -> None:
    manager = PaperActivityManager(db_path=tmp_path / "papers.db")
    with pytest.raises(KeyError):
        manager.update_activity("missing:1", user_notes="x")
