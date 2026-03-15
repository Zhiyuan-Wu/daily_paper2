"""Configuration utilities for the paper fetching module.

This module centralizes config loading from the repository-level ``config.yaml``.
All important defaults used by ``PaperFetch``, data sources and CLI should be read
from this file instead of being hardcoded in runtime logic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from service.common.config_loader import DEFAULT_CONFIG_PATH, load_app_config


def get_paper_fetch_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Return the ``paper_fetch`` section from config.

    Args:
        config_path: Optional config path override.

    Returns:
        The ``paper_fetch`` mapping.

    Raises:
        KeyError: If ``paper_fetch`` section is missing.
        ValueError: If ``paper_fetch`` is not a mapping.
    """
    config = load_app_config(config_path)
    if "paper_fetch" not in config:
        raise KeyError("Missing required config section: paper_fetch")

    section = config["paper_fetch"]
    if not isinstance(section, dict):
        raise ValueError("Config section 'paper_fetch' must be a mapping")
    return section
