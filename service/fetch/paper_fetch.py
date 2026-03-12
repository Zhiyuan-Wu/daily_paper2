"""Unified facade for online paper discovery and paper download."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from models.paper import PaperMetadata
from service.fetch.config import get_paper_fetch_config
from service.fetch.repository import PaperRepository
from service.fetch.sources.arxiv_source import ArxivPaperSource
from service.fetch.sources.base import PaperSource
from service.fetch.sources.huggingface_source import HuggingFacePaperSource


class PaperFetch:
    """Entry-point class that hides source-specific differences.

    This class provides three high-level capabilities:
    1. ``search_online``: query metadata from a selected remote source.
    2. ``download_paper``: download one paper PDF and update local metadata.
    """

    def __init__(
        self,
        db_path: str | Path | None = None,
        papers_dir: str | Path | None = None,
        max_downloaded_papers: int | None = None,
        hf_proxy_url: str | None = None,
        config_path: str | Path | None = None,
    ) -> None:
        """Initialize fetch service and built-in source plugins.

        Args:
            db_path: Optional sqlite path override. Defaults to config value.
            papers_dir: Optional paper directory override. Defaults to config value.
            max_downloaded_papers: Optional LRU capacity override.
            hf_proxy_url: Optional HuggingFace proxy override.
            config_path: Optional path to ``config.yaml``.
        """
        self.config = get_paper_fetch_config(config_path)
        source_cfg = _as_mapping(self.config.get("sources"), "paper_fetch.sources")
        arxiv_cfg = _as_mapping(source_cfg.get("arxiv"), "paper_fetch.sources.arxiv")
        hf_cfg = _as_mapping(source_cfg.get("huggingface"), "paper_fetch.sources.huggingface")
        cli_cfg = _as_mapping(self.config.get("cli"), "paper_fetch.cli")

        resolved_db_path = db_path or _as_str(self.config.get("db_path"), "paper_fetch.db_path")
        resolved_papers_dir = papers_dir or _as_str(self.config.get("papers_dir"), "paper_fetch.papers_dir")

        resolved_max_downloaded = (
            max_downloaded_papers
            if max_downloaded_papers is not None
            else _as_int(self.config.get("max_downloaded_papers"), "paper_fetch.max_downloaded_papers")
        )

        resolved_hf_proxy = hf_proxy_url or _as_str(
            hf_cfg.get("proxy_url"), "paper_fetch.sources.huggingface.proxy_url"
        )

        self.db_path = Path(resolved_db_path)
        self.papers_dir = Path(resolved_papers_dir)
        self.papers_dir.mkdir(parents=True, exist_ok=True)

        self.repo = PaperRepository(self.db_path)
        self.max_downloaded_papers = resolved_max_downloaded
        self.default_online_limit = _as_int(cli_cfg.get("default_online_limit"), "paper_fetch.cli.default_online_limit")
        self.sources: dict[str, PaperSource] = {}

        # Register built-in sources with config-driven defaults.
        self.register_source(
            ArxivPaperSource(
                timeout=_as_int(arxiv_cfg.get("timeout_seconds"), "paper_fetch.sources.arxiv.timeout_seconds"),
                default_query=_as_str(arxiv_cfg.get("default_query"), "paper_fetch.sources.arxiv.default_query"),
                default_search_limit=_as_int(
                    arxiv_cfg.get("default_search_limit"), "paper_fetch.sources.arxiv.default_search_limit"
                ),
                max_results_multiplier=_as_int(
                    arxiv_cfg.get("max_results_multiplier"),
                    "paper_fetch.sources.arxiv.max_results_multiplier",
                ),
                download_chunk_size=_as_int(
                    arxiv_cfg.get("download_chunk_size"),
                    "paper_fetch.sources.arxiv.download_chunk_size",
                ),
                config_path=config_path,
            )
        )
        self.register_source(
            HuggingFacePaperSource(
                proxy_url=resolved_hf_proxy,
                timeout=_as_int(hf_cfg.get("timeout_seconds"), "paper_fetch.sources.huggingface.timeout_seconds"),
                use_proxy=_as_bool(hf_cfg.get("use_proxy"), "paper_fetch.sources.huggingface.use_proxy"),
                download_chunk_size=_as_int(
                    hf_cfg.get("download_chunk_size"),
                    "paper_fetch.sources.huggingface.download_chunk_size",
                ),
                default_search_limit=_as_int(
                    hf_cfg.get("default_search_limit"), "paper_fetch.sources.huggingface.default_search_limit"
                ),
                config_path=config_path,
            )
        )

    def register_source(self, source: PaperSource) -> None:
        """Register an additional source plugin at runtime."""
        self.sources[source.name] = source

    def search_online(
        self,
        source: str,
        start_date: date | datetime | str | None = None,
        end_date: date | datetime | str | None = None,
        keywords: list[str] | str | None = None,
        limit: int | None = None,
        **source_kwargs: object,
    ) -> list[PaperMetadata]:
        """Query paper metadata from a remote source and persist results.

        Args:
            source: Source name, e.g. ``arxiv`` or ``huggingface``.
            start_date: Inclusive start date.
            end_date: Inclusive end date.
            keywords: Optional keyword list or comma-separated string.
            limit: Max number of returned results. Uses config default when None.
            **source_kwargs: Source-specific extension arguments.

        Returns:
            Unified list of ``PaperMetadata`` objects.
        """
        src = self._require_source(source)
        start = _as_date(start_date)
        end = _as_date(end_date)
        keyword_list = _as_keywords(keywords)
        resolved_limit = limit if limit is not None else self.default_online_limit

        papers = src.search(
            start_date=start,
            end_date=end,
            keywords=keyword_list,
            limit=resolved_limit,
            **source_kwargs,
        )

        # Online search only inserts missing rows, never mutates existing local records.
        self.repo.insert_papers_if_missing(papers)
        return papers

    def download_paper(
        self,
        paper_id: str,
        source: str | None = None,
        target_dir: str | Path | None = None,
        force_refresh: bool = False,
        **download_kwargs: object,
    ) -> PaperMetadata:
        """Download a paper PDF and update local metadata.

        Args:
            paper_id: Internal id (``source:source_id``) or source id.
            source: Required only when ``paper_id`` is source id.
            target_dir: Optional download directory override.
            force_refresh: If ``True``, ignore local cache and re-download.
            **download_kwargs: Source-specific download arguments.

        Returns:
            Updated ``PaperMetadata`` with refreshed ``local_pdf_path``.
        """
        paper = self.repo.get_by_id(paper_id)

        # If internal id format is used, split it and attempt source-specific lookup.
        if paper is None and ":" in paper_id:
            source_name, source_id = paper_id.split(":", 1)
            source = source or source_name
            paper = self.repo.get_by_source_id(source_name, source_id)
            if paper is None:
                src = self._require_source(source_name)
                paper = src.fetch_by_id(source_id, **download_kwargs)
                if paper:
                    self.repo.upsert_papers([paper])

        if paper is None:
            if source is None:
                raise ValueError("Paper not found in local DB. Provide source to fetch online by id.")
            src = self._require_source(source)
            paper = self.repo.get_by_source_id(source, paper_id)
            if paper is None:
                fetched = src.fetch_by_id(paper_id, **download_kwargs)
                if not fetched:
                    raise ValueError(f"Paper not found online: source={source}, id={paper_id}")
                paper = fetched
                self.repo.upsert_papers([paper])

        src = self._require_source(paper.source)
        out_dir = Path(target_dir) if target_dir else self.papers_dir

        # Determine where the file should be located for this download request.
        # If the target already exists and refresh is not forced, skip network I/O.
        target_path = self._default_pdf_path(out_dir, paper.id)
        if not force_refresh and target_path.exists():
            self.repo.update_download_path(paper.id, str(target_path))
            updated = self.repo.get_by_id(paper.id)
            if not updated:
                raise RuntimeError("Paper unexpectedly missing after cache update")
            return updated

        # Prefer the previously downloaded local cache when available.
        if not force_refresh and paper.local_pdf_path:
            cached_path = Path(paper.local_pdf_path)
            if cached_path.exists():
                self.repo.touch_access(paper.id)
                updated = self.repo.get_by_id(paper.id)
                if not updated:
                    raise RuntimeError("Paper unexpectedly missing after cache access touch")
                return updated

        local_path = src.download(paper, out_dir, **download_kwargs)

        # Persist local file path and timestamps in sqlite before LRU cleanup.
        self.repo.update_download_path(paper.id, str(local_path))
        self._apply_lru()

        updated = self.repo.get_by_id(paper.id)
        if not updated:
            raise RuntimeError("Paper unexpectedly missing after download update")
        return updated

    @staticmethod
    def _default_pdf_path(target_dir: Path, paper_id: str) -> Path:
        """Build the deterministic local file path used by built-in sources."""
        return target_dir / f"{paper_id.replace(':', '_')}.pdf"

    def _apply_lru(self) -> None:
        """Evict oldest downloaded PDFs when local cache exceeds the capacity."""
        if self.max_downloaded_papers <= 0:
            return

        downloaded = self.repo.list_downloaded_by_lru()
        overflow = len(downloaded) - self.max_downloaded_papers
        if overflow <= 0:
            return

        for old_paper in downloaded[:overflow]:
            if old_paper.local_pdf_path:
                try:
                    Path(old_paper.local_pdf_path).unlink(missing_ok=True)
                except OSError:
                    # File deletion failure should not break metadata consistency.
                    pass
            self.repo.clear_download_path(old_paper.id)

    def _require_source(self, source: str) -> PaperSource:
        """Return source plugin or raise a clear error for unsupported name."""
        if source not in self.sources:
            raise ValueError(f"Unsupported source '{source}'. Available: {sorted(self.sources)}")
        return self.sources[source]


# Backward-compatible alias for the user requested class name style.
Paper_Fetch = PaperFetch


def _as_keywords(keywords: list[str] | str | None) -> list[str] | None:
    """Normalize keyword input into ``list[str]`` or ``None``."""
    if keywords is None:
        return None
    if isinstance(keywords, str):
        values = [item.strip() for item in keywords.split(",") if item.strip()]
        return values or None
    cleaned = [item.strip() for item in keywords if item.strip()]
    return cleaned or None


def _as_date(value: date | datetime | str | None) -> date | None:
    """Convert date-like input to ``date`` for search APIs."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(value).date()


def _as_mapping(value: Any, key_name: str) -> dict[str, Any]:
    """Validate a config node as mapping and cast it."""
    if not isinstance(value, dict):
        raise ValueError(f"Config '{key_name}' must be a mapping")
    return value


def _as_str(value: Any, key_name: str) -> str:
    """Validate and cast a config value to string."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Config '{key_name}' must be a non-empty string")
    return value


def _as_int(value: Any, key_name: str) -> int:
    """Validate and cast a config value to integer."""
    if not isinstance(value, int):
        raise ValueError(f"Config '{key_name}' must be an integer")
    return value


def _as_bool(value: Any, key_name: str) -> bool:
    """Validate and cast a config value to bool."""
    if not isinstance(value, bool):
        raise ValueError(f"Config '{key_name}' must be a boolean")
    return value
