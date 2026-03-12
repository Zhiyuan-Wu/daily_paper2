"""Async subprocess task management for website backend."""

from __future__ import annotations

import subprocess
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    STOPPED = "stopped"


TERMINAL_STATUSES = {TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.STOPPED}


@dataclass(slots=True)
class ManagedTask:
    task_id: str
    task_type: str
    command: list[str]
    metadata: dict[str, Any]
    status: TaskStatus
    log_path: Path
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    pid: int | None = None
    return_code: int | None = None
    error: str | None = None
    stop_requested: bool = False
    process: subprocess.Popen[str] | None = field(default=None, repr=False)


class TaskManager:
    """Manage lifecycle of background subprocesses and log files."""

    def __init__(self, tasks_dir: str | Path) -> None:
        self.tasks_dir = Path(tasks_dir)
        self.tasks_dir.mkdir(parents=True, exist_ok=True)

        self._tasks: dict[str, ManagedTask] = {}
        self._lock = threading.Lock()

    def create_task(self, *, task_type: str, command: list[str], metadata: dict[str, Any]) -> dict[str, Any]:
        task_id = uuid.uuid4().hex[:12]
        log_path = self.tasks_dir / f"task-{task_id}.log"

        task = ManagedTask(
            task_id=task_id,
            task_type=task_type,
            command=command,
            metadata=metadata,
            status=TaskStatus.QUEUED,
            log_path=log_path,
            created_at=_utc_now(),
        )

        with self._lock:
            self._tasks[task_id] = task

        thread = threading.Thread(target=self._run_task, args=(task_id,), daemon=True)
        thread.start()

        return self.get_task(task_id)

    def list_tasks(self, *, status: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            tasks = list(self._tasks.values())

        if status:
            tasks = [item for item in tasks if item.status.value == status]

        tasks.sort(key=lambda item: item.created_at, reverse=True)
        return [self._snapshot(task) for task in tasks]

    def get_task(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                raise KeyError(task_id)
            return self._snapshot(task)

    def stop_task(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                raise KeyError(task_id)

            if task.status in TERMINAL_STATUSES:
                return self._snapshot(task)

            task.stop_requested = True
            process = task.process

            if task.status == TaskStatus.QUEUED and process is None:
                task.status = TaskStatus.STOPPED
                task.finished_at = _utc_now()
                return self._snapshot(task)

        if process and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass

        return self.get_task(task_id)

    def read_logs(self, task_id: str, *, offset: int = 0, limit: int = 64_000) -> dict[str, Any]:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                raise KeyError(task_id)
            log_path = task.log_path

        if offset < 0:
            raise ValueError("offset must be >= 0")

        if not log_path.exists():
            return {
                "task_id": task_id,
                "offset": offset,
                "next_offset": offset,
                "content": "",
                "completed": self.get_task(task_id)["status"] in {"success", "failed", "stopped"},
            }

        with log_path.open("rb") as handle:
            handle.seek(offset)
            chunk = handle.read(limit)
            next_offset = offset + len(chunk)

        return {
            "task_id": task_id,
            "offset": offset,
            "next_offset": next_offset,
            "content": chunk.decode("utf-8", errors="replace"),
            "completed": self.get_task(task_id)["status"] in {"success", "failed", "stopped"},
        }

    def _run_task(self, task_id: str) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return

            if task.status == TaskStatus.STOPPED:
                return

            task.status = TaskStatus.RUNNING
            task.started_at = _utc_now()

        task.log_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with task.log_path.open("a", encoding="utf-8") as log_handle:
                try:
                    process = subprocess.Popen(
                        task.command,
                        stdout=log_handle,
                        stderr=subprocess.STDOUT,
                        text=True,
                    )
                except Exception as exc:  # noqa: BLE001
                    log_handle.write(f"Failed to start command: {exc}\n")
                    with self._lock:
                        task.status = TaskStatus.FAILED
                        task.error = str(exc)
                        task.finished_at = _utc_now()
                    return

                with self._lock:
                    task.process = process
                    task.pid = process.pid

                return_code = process.wait()

            with self._lock:
                task.process = None
                task.return_code = return_code
                task.finished_at = _utc_now()
                if task.stop_requested:
                    task.status = TaskStatus.STOPPED
                elif return_code == 0:
                    task.status = TaskStatus.SUCCESS
                else:
                    task.status = TaskStatus.FAILED

        except Exception as exc:  # noqa: BLE001
            with self._lock:
                task.process = None
                task.status = TaskStatus.FAILED
                task.error = str(exc)
                task.finished_at = _utc_now()

    def _snapshot(self, task: ManagedTask) -> dict[str, Any]:
        now = _utc_now()
        end = task.finished_at or now
        running_seconds = 0.0
        if task.started_at:
            running_seconds = max((end - task.started_at).total_seconds(), 0.0)

        return {
            "task_id": task.task_id,
            "task_type": task.task_type,
            "metadata": task.metadata,
            "status": task.status.value,
            "command": task.command,
            "log_path": str(task.log_path),
            "created_at": task.created_at.isoformat(),
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "finished_at": task.finished_at.isoformat() if task.finished_at else None,
            "running_seconds": running_seconds,
            "pid": task.pid,
            "return_code": task.return_code,
            "error": task.error,
        }


class SkillCommandBuilder:
    """Build claude task commands from skill files."""

    def __init__(self, skills_dir: str | Path) -> None:
        self.skills_dir = Path(skills_dir)

    def build_report_generation(self, report_date: str) -> tuple[list[str], dict[str, Any], str]:
        skill_path = self.skills_dir / "paper-recommand" / "SKILL.md"
        prompt = f"Today is {report_date}."
        command = self._build_claude_command(skill_path, prompt)
        metadata = {
            "report_date": report_date,
            "skill_file_path": str(skill_path),
        }
        return command, metadata, "paper_recommand"

    def build_paper_analysis(self, paper_id: str) -> tuple[list[str], dict[str, Any], str]:
        skill_path = self.skills_dir / "paper-analysis" / "SKILL.md"
        prompt = f"Target Paper is {paper_id}."
        command = self._build_claude_command(skill_path, prompt)
        metadata = {
            "paper_id": paper_id,
            "skill_file_path": str(skill_path),
        }
        return command, metadata, "paper_analysis"

    @staticmethod
    def _build_claude_command(skill_path: Path, prompt: str = "") -> list[str]:
        if not skill_path.exists():
            raise FileNotFoundError(f"Skill file not found: {skill_path}")

        _prompt = f"Execute workflow in {skill_path}. {prompt}"
        return ["claude", "-p", _prompt, "--permission-mode", "bypassPermissions"]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
