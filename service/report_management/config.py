"""Configuration utilities for paper daily report management module."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.yaml"


def load_app_config(config_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"Config root must be a mapping object: {path}")
    return raw


def get_paper_report_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Return ``paper_report`` section with compatibility fallback."""
    cfg = load_app_config(config_path)
    section = cfg.get("paper_report")
    if section is not None:
        if not isinstance(section, dict):
            raise ValueError("Config section 'paper_report' must be a mapping")
        return section

    fetch_cfg = cfg.get("paper_fetch") if isinstance(cfg.get("paper_fetch"), dict) else {}
    db_path = str(fetch_cfg.get("db_path") or "data/papers.db")
    return {
        "db_path": db_path,
        "table_name": "report",
        "reports_dir": "data/reports",
        "cli": {"default_limit": 100},
    }
