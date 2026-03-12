from __future__ import annotations

import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from models.paper import PaperMetadata
from models.paper_activity import PaperActivityRecord
from models.paper_report import PaperReportRecord
from service.activity_management.repository import PaperActivityRepository
from service.fetch.repository import PaperRepository
from service.report_management.repository import PaperReportRepository
from website.backend.api import create_app
from website.backend.settings import BackendSettings


class FakeCommandBuilder:
    def build_report_generation(self, report_date: str):
        command = [
            sys.executable,
            "-c",
            (
                "import time; "
                f"print('report-{report_date}', flush=True); "
                "time.sleep(0.1); "
                "print('report-done', flush=True)"
            ),
        ]
        metadata = {"report_date": report_date, "skill_file_path": "/fake/paper-recommand/SKILL.md"}
        return command, metadata, "paper_recommand"

    def build_paper_analysis(self, paper_id: str):
        command = [
            sys.executable,
            "-c",
            (
                "import time; "
                f"print('analysis-{paper_id}', flush=True); "
                "time.sleep(0.1); "
                "print('analysis-done', flush=True)"
            ),
        ]
        metadata = {"paper_id": paper_id, "skill_file_path": "/fake/paper-analysis/SKILL.md"}
        return command, metadata, "paper_analysis"


def _prepare_test_data(tmp_path: Path) -> tuple[TestClient, str, str]:
    db_path = tmp_path / "papers-test.db"
    markdown_dir = tmp_path / "reports"
    markdown_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = markdown_dir / "daily-2026-03-11.md"
    markdown_path.write_text("# Daily Report\n\n- item\n", encoding="utf-8")

    paper_repo = PaperRepository(db_path)
    paper_repo.upsert_papers(
        [
            PaperMetadata(
                id="arxiv:2603.00001",
                source="arxiv",
                source_id="2603.00001",
                title="Agentic Critical Training",
                authors=["Alice", "Bob"],
                published_at=datetime(2026, 3, 9, 10, 0, tzinfo=timezone.utc),
                abstract="study on agents",
                online_url="https://example.org/paper-1",
                pdf_url="https://example.org/paper-1.pdf",
                extra={"keywords": ["agents", "llm"]},
            ),
            PaperMetadata(
                id="arxiv:2603.00002",
                source="arxiv",
                source_id="2603.00002",
                title="Lossless Audio Modeling",
                authors=["Carol"],
                published_at=datetime(2026, 3, 8, 10, 0, tzinfo=timezone.utc),
                abstract="audio compression",
                online_url="https://example.org/paper-2",
                pdf_url="",
                extra={"categories": ["cs.SD"]},
            ),
        ]
    )

    activity_repo = PaperActivityRepository(db_path)
    activity_repo.create(
        PaperActivityRecord(
            id="arxiv:2603.00001",
            recommendation_records=["2026-03-11T08:00:00+00:00"],
            user_notes="initial note",
            ai_report_summary="summary",
            ai_report_path="data/reports/a.md",
            like=1,
        )
    )

    report_repo = PaperReportRepository(db_path)
    report_repo.create(
        PaperReportRecord(
            id="daily-2026-03-11",
            report_date="2026-03-11",
            generated_at="2026-03-11T09:00:00+00:00",
            related_paper_ids=["arxiv:2603.00001", "arxiv:2603.00002"],
            local_md_path=str(markdown_path),
        )
    )

    settings = BackendSettings(
        db_path=db_path,
        tasks_dir=tmp_path / "task-logs",
        skills_dir=tmp_path / "skills",
        cors_origins=["*"],
    )
    app = create_app(settings=settings, command_builder=FakeCommandBuilder())
    return TestClient(app), str(markdown_path), str(db_path)


def _wait_for_terminal(client: TestClient, task_id: str, timeout: float = 4.0) -> str:
    deadline = time.time() + timeout
    last_status = ""
    while time.time() < deadline:
        res = client.get(f"/api/tasks/{task_id}")
        assert res.status_code == 200
        last_status = res.json()["status"]
        if last_status in {"success", "failed", "stopped"}:
            return last_status
        time.sleep(0.05)
    raise AssertionError(f"Task {task_id} did not finish in time, last={last_status}")


def test_report_and_markdown_endpoints(tmp_path: Path) -> None:
    client, markdown_path, _ = _prepare_test_data(tmp_path)

    res = client.get("/api/reports/by-date", params={"date": "2026-03-11"})
    assert res.status_code == 200
    payload = res.json()
    assert payload["id"] == "daily-2026-03-11"

    papers = client.get("/api/reports/daily-2026-03-11/papers")
    assert papers.status_code == 200
    paper_rows = papers.json()
    assert len(paper_rows) == 2
    assert paper_rows[0]["keywords"] == ["agents", "llm"]
    assert paper_rows[0]["like"] == 1
    assert paper_rows[1]["keywords"] == ["cs.SD"]
    assert paper_rows[1]["like"] == 0

    markdown = client.get("/api/reports/daily-2026-03-11/markdown")
    assert markdown.status_code == 200
    md_payload = markdown.json()
    assert md_payload["local_md_path"] == markdown_path
    assert "# Daily Report" in md_payload["content"]

    missing = client.get("/api/reports/by-date", params={"date": "2026-03-12"})
    assert missing.status_code == 404


def test_explore_detail_notes_like_and_db_update(tmp_path: Path) -> None:
    client, _, db_path = _prepare_test_data(tmp_path)

    explore = client.get("/api/papers/explore", params={"page": 1, "page_size": 20, "keyword": "agent"})
    assert explore.status_code == 200
    explore_payload = explore.json()
    assert explore_payload["total"] == 1
    assert explore_payload["items"][0]["id"] == "arxiv:2603.00001"

    detail = client.get("/api/papers/arxiv:2603.00001/detail")
    assert detail.status_code == 200
    assert detail.json()["user_notes"] == "initial note"
    assert detail.json()["like"] == 1

    update = client.patch(
        "/api/activities/arxiv:2603.00001/notes",
        json={"user_notes": "updated from test"},
    )
    assert update.status_code == 200
    assert update.json()["user_notes"] == "updated from test"
    assert update.json()["like"] == 1

    like_update = client.patch(
        "/api/activities/arxiv:2603.00001/like",
        json={"like": -1},
    )
    assert like_update.status_code == 200
    assert like_update.json()["like"] == -1

    invalid_like = client.patch(
        "/api/activities/arxiv:2603.00001/like",
        json={"like": 2},
    )
    assert invalid_like.status_code == 422

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            'SELECT user_notes, "like" FROM activity WHERE id = ?',
            ("arxiv:2603.00001",),
        ).fetchone()
        assert row is not None
        assert row[0] == "updated from test"
        assert row[1] == -1
    finally:
        conn.close()


def test_task_flow_for_report_ai_and_stop(tmp_path: Path) -> None:
    client, _, _ = _prepare_test_data(tmp_path)

    report_task_res = client.post("/api/reports/generate", json={"report_date": "2026-03-11"})
    assert report_task_res.status_code == 200
    report_task_id = report_task_res.json()["task_id"]
    report_status = _wait_for_terminal(client, report_task_id)
    assert report_status == "success"

    logs = client.get(f"/api/tasks/{report_task_id}/logs", params={"offset": 0})
    assert logs.status_code == 200
    assert "report-2026-03-11" in logs.json()["content"]

    ai_task_res = client.post("/api/papers/arxiv:2603.00001/ai-interpret")
    assert ai_task_res.status_code == 200
    ai_task_id = ai_task_res.json()["task_id"]
    ai_status = _wait_for_terminal(client, ai_task_id)
    assert ai_status == "success"

    long_task = client.post(
        "/api/tasks",
        json={
            "task_type": "long_task",
            "command": [
                sys.executable,
                "-c",
                "import time; print('start', flush=True); time.sleep(2); print('end', flush=True)",
            ],
            "metadata": {"origin": "test"},
        },
    )
    assert long_task.status_code == 200
    long_task_id = long_task.json()["task_id"]

    # Give the process enough time to start, then stop it.
    time.sleep(0.2)
    stop = client.post(f"/api/tasks/{long_task_id}/stop")
    assert stop.status_code == 200

    stopped_status = _wait_for_terminal(client, long_task_id)
    assert stopped_status == "stopped"

    running = client.get("/api/tasks", params={"status": "running"})
    assert running.status_code == 200
    assert all(item["status"] == "running" for item in running.json())
