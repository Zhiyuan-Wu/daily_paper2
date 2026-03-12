from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _run_cli(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable,
        str(ROOT / "scripts/paper_activity_cli.py"),
        "--db-path",
        str(tmp_path / "papers.db"),
        *args,
    ]
    return subprocess.run(cmd, check=False, capture_output=True, text=True, cwd=str(ROOT))


@pytest.mark.e2e
def test_e2e_cli_crud_and_db_state(tmp_path: Path) -> None:
    paper_id = "arxiv:2603.05500"

    create = _run_cli(
        tmp_path,
        "create",
        paper_id,
        "--recommendation-time",
        "2026-03-08T10:00:00Z",
        "--user-notes",
        "note-1",
        "--ai-report-summary",
        "summary-1",
        "--ai-report-path",
        "data/reports/r1.md",
        "--like",
        "1",
    )
    assert create.returncode == 0, create.stderr
    create_payload = json.loads(create.stdout)
    assert create_payload["id"] == paper_id
    assert create_payload["recommendation_records"] == ["2026-03-08T10:00:00Z"]
    assert create_payload["like"] == 1

    append = _run_cli(tmp_path, "append-recommendation", paper_id, "2026-03-08T11:00:00Z")
    assert append.returncode == 0, append.stderr
    append_payload = json.loads(append.stdout)
    assert append_payload["recommendation_records"] == [
        "2026-03-08T10:00:00Z",
        "2026-03-08T11:00:00Z",
    ]

    update = _run_cli(
        tmp_path,
        "update",
        paper_id,
        "--user-notes",
        "note-2",
        "--ai-report-summary",
        "summary-2",
        "--like",
        "-1",
    )
    assert update.returncode == 0, update.stderr
    update_payload = json.loads(update.stdout)
    assert update_payload["user_notes"] == "note-2"
    assert update_payload["ai_report_summary"] == "summary-2"
    assert update_payload["like"] == -1

    get_one = _run_cli(tmp_path, "get", paper_id)
    assert get_one.returncode == 0, get_one.stderr
    get_payload = json.loads(get_one.stdout)
    assert get_payload["id"] == paper_id
    assert len(get_payload["recommendation_records"]) == 2

    list_rows = _run_cli(tmp_path, "list", "--limit", "10")
    assert list_rows.returncode == 0, list_rows.stderr
    list_payload = json.loads(list_rows.stdout)
    assert len(list_payload) == 1
    assert list_payload[0]["id"] == paper_id

    conn = sqlite3.connect(tmp_path / "papers.db")
    try:
        row = conn.execute(
            'SELECT recommendation_records, user_notes, ai_report_summary, ai_report_path, "like" FROM activity WHERE id = ?',
            (paper_id,),
        ).fetchone()
        assert row is not None
        assert json.loads(row[0]) == ["2026-03-08T10:00:00Z", "2026-03-08T11:00:00Z"]
        assert row[1] == "note-2"
        assert row[2] == "summary-2"
        assert row[3] == "data/reports/r1.md"
        assert row[4] == -1
    finally:
        conn.close()

    delete = _run_cli(tmp_path, "delete", paper_id)
    assert delete.returncode == 0, delete.stderr
    delete_payload = json.loads(delete.stdout)
    assert delete_payload["deleted"] is True

    conn = sqlite3.connect(tmp_path / "papers.db")
    try:
        row = conn.execute("SELECT 1 FROM activity WHERE id = ?", (paper_id,)).fetchone()
        assert row is None
    finally:
        conn.close()
