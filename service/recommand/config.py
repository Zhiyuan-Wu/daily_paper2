"""Configuration utilities for paper recommendation module."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from service.common.config_loader import DEFAULT_CONFIG_PATH, load_app_config


def get_paper_recommand_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Return ``paper_recommand`` section with compatibility fallback."""
    cfg = load_app_config(config_path)
    section = cfg.get("paper_recommand")
    if section is not None:
        if not isinstance(section, dict):
            raise ValueError("Config section 'paper_recommand' must be a mapping")
        return section

    fetch_cfg = cfg.get("paper_fetch") if isinstance(cfg.get("paper_fetch"), dict) else {}
    db_path = str(fetch_cfg.get("db_path") or "data/papers.db")
    return {
        "db_path": db_path,
        "paper_table": "papers",
        "activity_table": "activity",
        "default_algorithm": "fusion",
        "default_top_k": 20,
        "plugins": {
            "semantic": {
                "enabled": True,
                "top_k": 20,
                "weight": 1.0,
            },
            "interaction": {
                "enabled": True,
                "like_weight": 0.45,
                "note_weight": 0.55,
                "dislike_penalty": 0.4,
                "recommended_penalty": 0.08,
                "weight": 1.0,
            },
            "time": {
                "enabled": True,
                "freshness_window_days": 30,
                "weight": 1.0,
            },
        },
    }
