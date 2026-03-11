"""FastAPI application for daily_paper2 website backend."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from website.backend.database import SQLiteDataStore
from website.backend.settings import ROOT_DIR, BackendSettings, load_settings
from website.backend.tasks import SkillCommandBuilder, TaskManager


class NotesUpdateRequest(BaseModel):
    user_notes: str = Field(default="", max_length=50_000)


class GenerateReportRequest(BaseModel):
    report_date: str | None = None


class GenericTaskRequest(BaseModel):
    task_type: str
    command: list[str]
    metadata: dict[str, Any] = Field(default_factory=dict)


class StopTaskResponse(BaseModel):
    task: dict[str, Any]


def create_app(
    *,
    settings: BackendSettings | None = None,
    data_store: SQLiteDataStore | None = None,
    task_manager: TaskManager | None = None,
    command_builder: SkillCommandBuilder | None = None,
) -> FastAPI:
    cfg = settings or load_settings()

    app = FastAPI(title="daily_paper2 backend", version="1.0.0")

    allow_credentials = cfg.cors_origins != ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.data_store = data_store or SQLiteDataStore(cfg.db_path)
    app.state.task_manager = task_manager or TaskManager(cfg.tasks_dir)
    app.state.command_builder = command_builder or SkillCommandBuilder(cfg.skills_dir)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/reports/by-date")
    def get_report_by_date(date: str = Query(..., description="YYYY-MM-DD")) -> dict[str, Any]:
        _validate_iso_date(date)

        report = app.state.data_store.get_report_by_date(date)
        if not report:
            raise HTTPException(status_code=404, detail="Report not found")
        return report

    @app.get("/api/reports/{report_id}/papers")
    def get_report_papers(report_id: str) -> list[dict[str, Any]]:
        try:
            return app.state.data_store.list_report_papers(report_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Report not found") from exc

    @app.get("/api/reports/{report_id}/markdown")
    def get_report_markdown(report_id: str) -> dict[str, Any]:
        report = app.state.data_store.get_report(report_id)
        if not report:
            raise HTTPException(status_code=404, detail="Report not found")

        local_md_path = report.get("local_md_path") or ""
        if not local_md_path:
            raise HTTPException(status_code=404, detail="Markdown path is empty")

        path = Path(local_md_path)
        if not path.is_absolute():
            path = ROOT_DIR / path
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail="Markdown file not found")

        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"Failed to read markdown file: {exc}") from exc

        return {
            "report_id": report_id,
            "local_md_path": str(path),
            "content": content,
        }

    @app.post("/api/reports/generate")
    def generate_report_task(payload: GenerateReportRequest) -> dict[str, Any]:
        report_date = payload.report_date or date.today().isoformat()
        _validate_iso_date(report_date)

        try:
            command, metadata, task_type = app.state.command_builder.build_report_generation(report_date)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        task = app.state.task_manager.create_task(
            task_type=task_type,
            command=command,
            metadata=metadata,
        )
        return {"task_id": task["task_id"], "status": task["status"], "task": task}

    @app.get("/api/papers/explore")
    def explore_papers(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        keyword: str = Query(""),
        source: str = Query(""),
    ) -> dict[str, Any]:
        return app.state.data_store.list_explore_papers(
            page=page,
            page_size=page_size,
            keyword=keyword or None,
            source=source or None,
        )

    @app.get("/api/papers/{paper_id}/detail")
    def paper_detail(paper_id: str) -> dict[str, Any]:
        detail = app.state.data_store.get_paper_detail(paper_id)
        if not detail:
            raise HTTPException(status_code=404, detail="Paper not found")
        return detail

    @app.patch("/api/activities/{paper_id}/notes")
    def update_activity_notes(paper_id: str, payload: NotesUpdateRequest) -> dict[str, Any]:
        try:
            updated = app.state.data_store.update_user_notes(paper_id, payload.user_notes)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Paper not found") from exc
        return updated

    @app.post("/api/papers/{paper_id}/ai-interpret")
    def create_ai_interpret_task(paper_id: str) -> dict[str, Any]:
        if not app.state.data_store.paper_exists(paper_id):
            raise HTTPException(status_code=404, detail="Paper not found")

        try:
            command, metadata, task_type = app.state.command_builder.build_paper_analysis(paper_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        task = app.state.task_manager.create_task(
            task_type=task_type,
            command=command,
            metadata=metadata,
        )
        return {"task_id": task["task_id"], "status": task["status"], "task": task}

    @app.post("/api/tasks")
    def create_generic_task(payload: GenericTaskRequest) -> dict[str, Any]:
        if not payload.command:
            raise HTTPException(status_code=422, detail="command must not be empty")

        task = app.state.task_manager.create_task(
            task_type=payload.task_type,
            command=payload.command,
            metadata=payload.metadata,
        )
        return {"task_id": task["task_id"], "status": task["status"], "task": task}

    @app.get("/api/tasks")
    def list_tasks(status: str = Query("")) -> list[dict[str, Any]]:
        return app.state.task_manager.list_tasks(status=status or None)

    @app.get("/api/tasks/{task_id}")
    def get_task(task_id: str) -> dict[str, Any]:
        try:
            return app.state.task_manager.get_task(task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Task not found") from exc

    @app.post("/api/tasks/{task_id}/stop", response_model=StopTaskResponse)
    def stop_task(task_id: str) -> StopTaskResponse:
        try:
            task = app.state.task_manager.stop_task(task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Task not found") from exc
        return StopTaskResponse(task=task)

    @app.get("/api/tasks/{task_id}/logs")
    def get_task_logs(
        task_id: str,
        offset: int = Query(0, ge=0),
        limit: int = Query(64_000, ge=1, le=500_000),
    ) -> dict[str, Any]:
        try:
            return app.state.task_manager.read_logs(task_id, offset=offset, limit=limit)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Task not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return app


def _validate_iso_date(raw: str) -> str:
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="date must be YYYY-MM-DD") from exc
