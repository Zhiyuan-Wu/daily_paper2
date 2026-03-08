"""Plugin abstraction for paper sources.

Each source plugin only needs to implement three operations:
1. search metadata
2. fetch one metadata by source-id
3. download paper PDF
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from pathlib import Path

from models.paper import PaperMetadata


class PaperSource(ABC):
    """Abstract base class for source-specific adapters."""

    name: str

    @abstractmethod
    def search(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
        keywords: list[str] | None = None,
        limit: int | None = None,
        **kwargs: object,
    ) -> list[PaperMetadata]:
        """Search paper metadata from an online source."""

    @abstractmethod
    def fetch_by_id(self, source_id: str, **kwargs: object) -> PaperMetadata | None:
        """Fetch one paper metadata by source-specific id."""

    @abstractmethod
    def download(self, paper: PaperMetadata, target_dir: Path, **kwargs: object) -> Path:
        """Download a paper PDF and return the local path."""

    def _build_internal_id(self, source_id: str) -> str:
        """Build stable internal id using ``source:source_id`` format."""
        return f"{self.name}:{source_id}"
