from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from models.paper_report import PaperReportRecord
from service.report_management.report_manager import DailyReportManager


def test_model_roundtrip() -> None:
    record = PaperReportRecord(
        id="daily-2026-03-11",
        report_date="2026-03-11",
        generated_at="2026-03-11T08:30:00+00:00",
        related_paper_ids=["arxiv:2603.05500", "huggingface:paper-1"],
        local_md_path="data/reports/daily-2026-03-11.md",
    )
    row = record.to_db_row()
    restored = PaperReportRecord.from_db_row(row)
    assert restored.id == record.id
    assert restored.report_date == "2026-03-11"
    assert restored.generated_at == "2026-03-11T08:30:00+00:00"
    assert restored.related_paper_ids == record.related_paper_ids
    assert restored.local_md_path == record.local_md_path


def test_crud_and_raw_json_state(tmp_path: Path) -> None:
    manager = DailyReportManager(db_path=tmp_path / "papers.db")
    report_id = "daily-2026-03-11"

    created = manager.create_report(
        report_id,
        report_date="2026-03-11",
        generated_at="2026-03-11T08:00:00+00:00",
        related_paper_ids=["arxiv:2603.05500"],
        local_md_path="data/reports/r1.md",
    )
    assert created.id == report_id
    assert created.related_paper_ids == ["arxiv:2603.05500"]

    loaded = manager.get_report(report_id)
    assert loaded is not None
    assert loaded.report_date == "2026-03-11"
    assert loaded.local_md_path == "data/reports/r1.md"

    updated = manager.update_report(
        report_id,
        generated_at="2026-03-11T09:00:00Z",
        related_paper_ids=["arxiv:2603.05500", "huggingface:paper-1"],
        local_md_path="data/reports/r2.md",
    )
    assert updated.generated_at == "2026-03-11T09:00:00+00:00"
    assert updated.related_paper_ids == ["arxiv:2603.05500", "huggingface:paper-1"]
    assert updated.local_md_path == "data/reports/r2.md"

    conn = sqlite3.connect(tmp_path / "papers.db")
    try:
        row = conn.execute(
            "SELECT report_date, generated_at, related_paper_ids, local_md_path FROM report WHERE id = ?",
            (report_id,),
        ).fetchone()
        assert row is not None
        assert row[0] == "2026-03-11"
        assert row[1] == "2026-03-11T09:00:00+00:00"
        assert json.loads(row[2]) == ["arxiv:2603.05500", "huggingface:paper-1"]
        assert row[3] == "data/reports/r2.md"
    finally:
        conn.close()

    deleted = manager.delete_report(report_id)
    assert deleted is True
    assert manager.get_report(report_id) is None


def test_list_with_report_date_filter(tmp_path: Path) -> None:
    manager = DailyReportManager(db_path=tmp_path / "papers.db")
    manager.create_report(
        "daily-2026-03-10",
        report_date="2026-03-10",
        generated_at="2026-03-10T08:00:00+00:00",
    )
    manager.create_report(
        "daily-2026-03-11",
        report_date="2026-03-11",
        generated_at="2026-03-11T08:00:00+00:00",
    )

    all_rows = manager.list_reports(limit=10)
    assert [row.id for row in all_rows] == ["daily-2026-03-11", "daily-2026-03-10"]

    filtered = manager.list_reports(limit=10, report_date="2026-03-10")
    assert len(filtered) == 1
    assert filtered[0].id == "daily-2026-03-10"


def test_update_missing_record_raises(tmp_path: Path) -> None:
    manager = DailyReportManager(db_path=tmp_path / "papers.db")
    with pytest.raises(KeyError):
        manager.update_report("missing", local_md_path="data/reports/x.md")
