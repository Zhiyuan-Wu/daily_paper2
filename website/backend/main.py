"""ASGI entrypoint for website backend."""

from __future__ import annotations

from website.backend.api import create_app

app = create_app()
