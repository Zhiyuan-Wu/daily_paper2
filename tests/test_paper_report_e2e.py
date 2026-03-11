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
        str(ROOT / "scripts/paper_report_cli.py"),
        "--db-path",
        str(tmp_path / "papers.db"),
        *args,
    ]
    return subprocess.run(cmd, check=False, capture_output=True, text=True, cwd=str(ROOT))


@pytest.mark.e2e
def test_e2e_cli_crud_and_db_state(tmp_path: Path) -> None:
    report_id = "daily-2026-03-11"

    create = _run_cli(
        tmp_path,
        "create",
        report_id,
        "--report-date",
        "2026-03-11",
        "--generated-at",
        "2026-03-11T08:00:00Z",
        "--paper-id",
        "arxiv:2603.05500",
        "--paper-id",
        "huggingface:paper-1",
        "--local-md-path",
        "data/reports/daily-2026-03-11.md",
    )
    assert create.returncode == 0, create.stderr
    create_payload = json.loads(create.stdout)
    assert create_payload["id"] == report_id
    assert create_payload["report_date"] == "2026-03-11"
    assert create_payload["generated_at"] == "2026-03-11T08:00:00+00:00"
    assert create_payload["related_paper_ids"] == ["arxiv:2603.05500", "huggingface:paper-1"]

    update = _run_cli(
        tmp_path,
        "update",
        report_id,
        "--generated-at",
        "2026-03-11T10:00:00+00:00",
        "--paper-id",
        "arxiv:2603.05500",
        "--local-md-path",
        "data/reports/daily-2026-03-11-v2.md",
    )
    assert update.returncode == 0, update.stderr
    update_payload = json.loads(update.stdout)
    assert update_payload["generated_at"] == "2026-03-11T10:00:00+00:00"
    assert update_payload["related_paper_ids"] == ["arxiv:2603.05500"]
    assert update_payload["local_md_path"] == "data/reports/daily-2026-03-11-v2.md"

    get_one = _run_cli(tmp_path, "get", report_id)
    assert get_one.returncode == 0, get_one.stderr
    get_payload = json.loads(get_one.stdout)
    assert get_payload["id"] == report_id

    list_rows = _run_cli(tmp_path, "list", "--limit", "10", "--report-date", "2026-03-11")
    assert list_rows.returncode == 0, list_rows.stderr
    list_payload = json.loads(list_rows.stdout)
    assert len(list_payload) == 1
    assert list_payload[0]["id"] == report_id

    conn = sqlite3.connect(tmp_path / "papers.db")
    try:
        row = conn.execute(
            "SELECT report_date, generated_at, related_paper_ids, local_md_path FROM report WHERE id = ?",
            (report_id,),
        ).fetchone()
        assert row is not None
        assert row[0] == "2026-03-11"
        assert row[1] == "2026-03-11T10:00:00+00:00"
        assert json.loads(row[2]) == ["arxiv:2603.05500"]
        assert row[3] == "data/reports/daily-2026-03-11-v2.md"
    finally:
        conn.close()

    delete = _run_cli(tmp_path, "delete", report_id)
    assert delete.returncode == 0, delete.stderr
    delete_payload = json.loads(delete.stdout)
    assert delete_payload["deleted"] is True

    conn = sqlite3.connect(tmp_path / "papers.db")
    try:
        row = conn.execute("SELECT 1 FROM report WHERE id = ?", (report_id,)).fetchone()
        assert row is None
    finally:
        conn.close()
