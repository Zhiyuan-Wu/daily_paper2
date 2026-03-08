"""Configuration utilities for the paper fetching module.

This module centralizes config loading from the repository-level ``config.yaml``.
All important defaults used by ``PaperFetch``, data sources and CLI should be read
from this file instead of being hardcoded in runtime logic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

# ``service/fetch/config.py`` -> project root is ``parents[2]``.
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.yaml"


def load_app_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Load and validate the YAML config file.

    Args:
        config_path: Optional explicit path to a YAML file. When omitted,
            ``DEFAULT_CONFIG_PATH`` is used.

    Returns:
        Parsed configuration dictionary.

    Raises:
        FileNotFoundError: If the config file does not exist.
        ValueError: If the YAML content is not a mapping object.
    """
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"Config root must be a mapping object: {path}")
    return raw


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
