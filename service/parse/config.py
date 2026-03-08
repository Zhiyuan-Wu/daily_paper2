"""Configuration utilities for paper parsing module."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.yaml"


def load_app_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Load YAML config from repository root by default."""
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"Config root must be a mapping object: {path}")
    return raw


def get_paper_parse_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Return ``paper_parse`` section, with compatibility fallbacks."""
    cfg = load_app_config(config_path)
    section = cfg.get("paper_parse")
    if section is not None:
        if not isinstance(section, dict):
            raise ValueError("Config section 'paper_parse' must be a mapping")
        return section

    # Backward-compatible fallback when parse config is not explicitly configured.
    fetch_cfg = cfg.get("paper_fetch") if isinstance(cfg.get("paper_fetch"), dict) else {}
    db_path = str(fetch_cfg.get("db_path") or "data/papers.db")
    return {
        "db_path": db_path,
        "parsed_dir": "data/parsed",
        "pdf": {"dpi": 200},
        "ollama": {
            "endpoint": "http://localhost:11434/api/chat",
            "model": "glm-ocr",
            "prompt": "Text Recognition:",
            "timeout_seconds": 120,
        },
    }
