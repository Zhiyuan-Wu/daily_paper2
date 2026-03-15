"""Shared SQLite safety utilities."""

from __future__ import annotations

import re

_TABLE_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def validate_table_name(table_name: str) -> str:
    """Validate sqlite identifier used as table name."""
    if not _TABLE_NAME_PATTERN.match(table_name):
        raise ValueError(f"Invalid sqlite table name: {table_name}")
    return table_name
