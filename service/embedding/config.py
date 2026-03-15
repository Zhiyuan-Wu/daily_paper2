"""Configuration utilities for paper embedding module."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from service.common.config_loader import DEFAULT_CONFIG_PATH, load_app_config


def get_paper_embedding_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Return ``paper_embedding`` section, with compatibility fallbacks."""
    cfg = load_app_config(config_path)
    section = cfg.get("paper_embedding")
    if section is not None:
        if not isinstance(section, dict):
            raise ValueError("Config section 'paper_embedding' must be a mapping")
        return section

    fetch_cfg = cfg.get("paper_fetch") if isinstance(cfg.get("paper_fetch"), dict) else {}
    db_path = str(fetch_cfg.get("db_path") or "data/papers.db")
    return {
        "db_path": db_path,
        "embedding_table": "paper_embeddings",
        "default_top_k": 5,
        "default_batch_size": 8,
        "ollama": {
            "endpoint": "http://localhost:11434/api/embed",
            "model": "qwen3-embedding:0.6b",
            "timeout_seconds": 120,
        },
    }
