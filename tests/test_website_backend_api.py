from __future__ import annotations

import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from models.paper import PaperMetadata
from models.paper_activity import PaperActivityRecord
from models.paper_extend_metadata import PaperExtendMetadataRecord
from models.paper_report import PaperReportRecord
from service.activity_management.repository import PaperActivityRepository
from service.extend_metadata.repository import PaperExtendMetadataRepository
from service.fetch.repository import PaperRepository
from service.report_management.repository import PaperReportRepository
from website.backend.api import _build_allowed_markdown_roots, _read_markdown_file, create_app
from website.backend.settings import BackendSettings, ROOT_DIR


class FakeCommandBuilder:
    def __init__(self, *, report_sleep_seconds: float = 0.1, analysis_sleep_seconds: float = 0.1):
        self.report_sleep_seconds = report_sleep_seconds
        self.analysis_sleep_seconds = analysis_sleep_seconds

    def build_report_generation(self, report_date: str):
        command = [
            sys.executable,
            "-c",
            (
                "import time; "
                f"print('report-{report_date}', flush=True); "
                f"time.sleep({self.report_sleep_seconds}); "
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
                f"time.sleep({self.analysis_sleep_seconds}); "
                "print('analysis-done', flush=True)"
            ),
        ]
        metadata = {"paper_id": paper_id, "skill_file_path": "/fake/paper-analysis/SKILL.md"}
        return command, metadata, "paper_analysis"


def _prepare_test_data(
    tmp_path: Path,
    *,
    command_builder: FakeCommandBuilder | None = None,
) -> tuple[TestClient, str, str]:
    db_path = tmp_path / "papers-test.db"
    markdown_dir = tmp_path / "reports"
    analysis_dir = tmp_path / "analysis"
    markdown_dir.mkdir(parents=True, exist_ok=True)
    analysis_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = markdown_dir / "daily-2026-03-11.md"
    ai_markdown_path = analysis_dir / "paper_analysis_arxiv_2603.00001_2026-03-11.md"
    markdown_path.write_text("# Daily Report\n\n- item\n", encoding="utf-8")
    ai_markdown_path.write_text("# AI Interpretation\n\n- key idea\n", encoding="utf-8")
    markdown_rel_path = markdown_path.relative_to(tmp_path)
    ai_markdown_rel_path = ai_markdown_path.relative_to(tmp_path)

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
            ai_report_path=str(ai_markdown_rel_path),
            like=1,
        )
    )

    extend_repo = PaperExtendMetadataRepository(db_path)
    extend_repo.upsert_record(
        PaperExtendMetadataRecord(
            paper_id="arxiv:2603.00001",
            abstract_cn="这是一篇关于智能体训练的中文摘要。",
            affliations=["OpenAI", "Tsinghua University"],
            keywords=["agent", "reasoning"],
            extracted_at=datetime(2026, 3, 11, 9, 0, tzinfo=timezone.utc),
        )
    )

    report_repo = PaperReportRepository(db_path)
    report_repo.create(
        PaperReportRecord(
            id="daily-2026-03-11",
            report_date="2026-03-11",
            generated_at="2026-03-11T09:00:00+00:00",
            related_paper_ids=["arxiv:2603.00001", "arxiv:2603.00002"],
            local_md_path=str(markdown_rel_path),
        )
    )

    settings = BackendSettings(
        db_path=db_path,
        tasks_dir=tmp_path / "task-logs",
        skills_dir=tmp_path / "skills",
        cors_origins=["*"],
    )
    app = create_app(settings=settings, command_builder=command_builder or FakeCommandBuilder())
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
    client, markdown_path, db_path = _prepare_test_data(tmp_path)

    res = client.get("/api/reports/by-date", params={"date": "2026-03-11"})
    assert res.status_code == 200
    payload = res.json()
    assert payload["id"] == "daily-2026-03-11"

    papers = client.get("/api/reports/daily-2026-03-11/papers")
    assert papers.status_code == 200
    paper_rows = papers.json()
    assert len(paper_rows) == 2
    assert paper_rows[0]["keywords"] == ["agent", "reasoning"]
    assert paper_rows[0]["affiliations"] == ["OpenAI", "Tsinghua University"]
    assert paper_rows[0]["abstract"] == "这是一篇关于智能体训练的中文摘要。"
    assert paper_rows[0]["like"] == 1
    assert paper_rows[1]["keywords"] == []
    assert paper_rows[1]["affiliations"] == []
    assert paper_rows[1]["abstract"] == "audio compression"
    assert paper_rows[1]["like"] == 0

    markdown = client.get("/api/reports/daily-2026-03-11/markdown")
    assert markdown.status_code == 200
    md_payload = markdown.json()
    assert md_payload["local_md_path"] == markdown_path
    assert "# Daily Report" in md_payload["content"]

    ai_markdown = client.get("/api/papers/arxiv:2603.00001/ai-interpret-markdown")
    assert ai_markdown.status_code == 200
    ai_payload = ai_markdown.json()
    assert ai_payload["paper_id"] == "arxiv:2603.00001"
    assert "paper_analysis_arxiv_2603.00001_2026-03-11.md" in ai_payload["local_md_path"]
    assert "# AI Interpretation" in ai_payload["content"]

    ai_missing = client.get("/api/papers/arxiv:2603.00002/ai-interpret-markdown")
    assert ai_missing.status_code == 404

    missing = client.get("/api/reports/by-date", params={"date": "2026-03-12"})
    assert missing.status_code == 404

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE report SET local_md_path = ? WHERE id = ?",
            ("/etc/hosts", "daily-2026-03-11"),
        )
        conn.execute(
            "UPDATE activity SET ai_report_path = ? WHERE id = ?",
            ("../../etc/hosts", "arxiv:2603.00001"),
        )
        conn.commit()
    finally:
        conn.close()

    report_abs = client.get("/api/reports/daily-2026-03-11/markdown")
    assert report_abs.status_code == 400
    assert report_abs.json()["detail"] == "Markdown path must be relative"

    ai_traversal = client.get("/api/papers/arxiv:2603.00001/ai-interpret-markdown")
    assert ai_traversal.status_code == 404


def test_explore_detail_notes_like_and_db_update(tmp_path: Path) -> None:
    client, _, db_path = _prepare_test_data(tmp_path)

    explore = client.get("/api/papers/explore", params={"page": 1, "page_size": 20, "keyword": "agent"})
    assert explore.status_code == 200
    explore_payload = explore.json()
    assert explore_payload["total"] == 1
    assert explore_payload["items"][0]["id"] == "arxiv:2603.00001"
    assert explore_payload["items"][0]["keywords"] == ["agent", "reasoning"]
    assert explore_payload["items"][0]["affiliations"] == ["OpenAI", "Tsinghua University"]
    assert explore_payload["items"][0]["abstract"] == "这是一篇关于智能体训练的中文摘要。"

    detail = client.get("/api/papers/arxiv:2603.00001/detail")
    assert detail.status_code == 200
    assert detail.json()["user_notes"] == "initial note"
    assert detail.json()["like"] == 1
    assert detail.json()["keywords"] == ["agent", "reasoning"]
    assert detail.json()["affiliations"] == ["OpenAI", "Tsinghua University"]
    assert detail.json()["abstract"] == "这是一篇关于智能体训练的中文摘要。"

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


def test_read_markdown_file_accepts_project_root_relative_data_path(tmp_path: Path) -> None:
    reports_dir = ROOT_DIR / "data" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = reports_dir / "test-daily-2026-03-15.md"
    markdown_path.write_text("# Test Report\n", encoding="utf-8")

    try:
        settings = BackendSettings(
            db_path=tmp_path / "papers-test.db",
            tasks_dir=tmp_path / "task-logs",
            skills_dir=tmp_path / "skills",
            cors_origins=["*"],
        )

        path, content = _read_markdown_file(
            "data/reports/test-daily-2026-03-15.md",
            allowed_roots=_build_allowed_markdown_roots(settings),
            not_found_detail="Markdown file not found",
            read_fail_prefix="Failed to read markdown file",
        )

        assert path == markdown_path.resolve()
        assert content == "# Test Report\n"
    finally:
        markdown_path.unlink(missing_ok=True)


def test_task_flow_for_report_ai_and_stop(tmp_path: Path) -> None:
    client, _, _ = _prepare_test_data(
        tmp_path,
        command_builder=FakeCommandBuilder(report_sleep_seconds=2.0, analysis_sleep_seconds=0.1),
    )

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

    stoppable_task = client.post("/api/reports/generate", json={"report_date": "2026-03-12"})
    assert stoppable_task.status_code == 200
    stoppable_task_id = stoppable_task.json()["task_id"]

    # Give the process enough time to start, then stop it.
    time.sleep(0.2)
    stop = client.post(f"/api/tasks/{stoppable_task_id}/stop")
    assert stop.status_code == 200

    stopped_status = _wait_for_terminal(client, stoppable_task_id)
    assert stopped_status == "stopped"

    generic_create = client.post(
        "/api/tasks",
        json={"task_type": "long_task", "command": [sys.executable, "-c", "print('x')"], "metadata": {}},
    )
    assert generic_create.status_code == 405

    running = client.get("/api/tasks", params={"status": "running"})
    assert running.status_code == 200
    assert all(item["status"] == "running" for item in running.json())
