"""Configuration utilities for paper activity management module."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from service.common.config_loader import DEFAULT_CONFIG_PATH, load_app_config


def get_paper_activity_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Return ``paper_activity`` section with compatibility fallback."""
    cfg = load_app_config(config_path)
    section = cfg.get("paper_activity")
    if section is not None:
        if not isinstance(section, dict):
            raise ValueError("Config section 'paper_activity' must be a mapping")
        return section

    fetch_cfg = cfg.get("paper_fetch") if isinstance(cfg.get("paper_fetch"), dict) else {}
    db_path = str(fetch_cfg.get("db_path") or "data/papers.db")
    return {
        "db_path": db_path,
        "table_name": "activity",
        "cli": {"default_limit": 100},
    }
