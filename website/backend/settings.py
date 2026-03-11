"""Runtime settings for website backend."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]


@dataclass(slots=True)
class BackendSettings:
    """Configuration sourced from environment variables."""

    db_path: Path
    tasks_dir: Path
    skills_dir: Path
    cors_origins: list[str]


def load_settings() -> BackendSettings:
    db_path_raw = os.getenv("DAILY_PAPER_DB_PATH", str(ROOT_DIR / "data" / "papers.db"))
    tasks_dir_raw = os.getenv("DAILY_PAPER_TASKS_DIR", str(ROOT_DIR / "data" / "task_logs"))
    skills_dir_raw = os.getenv("DAILY_PAPER_SKILLS_DIR", str(ROOT_DIR / "skills"))
    cors_raw = os.getenv("DAILY_PAPER_CORS_ORIGINS", "*")

    cors_origins = [origin.strip() for origin in cors_raw.split(",") if origin.strip()]
    if not cors_origins:
        cors_origins = ["*"]

    return BackendSettings(
        db_path=Path(db_path_raw).resolve(),
        tasks_dir=Path(tasks_dir_raw).resolve(),
        skills_dir=Path(skills_dir_raw).resolve(),
        cors_origins=cors_origins,
    )
