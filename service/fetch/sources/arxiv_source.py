"""arXiv source plugin implementation."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from pathlib import Path

import arxiv
import requests

from models.paper import PaperMetadata
from service.fetch.config import get_paper_fetch_config
from service.fetch.sources.base import PaperSource


class ArxivPaperSource(PaperSource):
    """Fetch paper metadata and PDFs from arXiv using the official ``arxiv`` package."""

    name = "arxiv"

    def __init__(
        self,
        timeout: int | None = None,
        default_query: str | None = None,
        default_search_limit: int | None = None,
        max_results_multiplier: int | None = None,
        download_chunk_size: int | None = None,
        config_path: str | Path | None = None,
    ) -> None:
        """Initialize arXiv source with config-driven defaults."""
        cfg = get_paper_fetch_config(config_path)["sources"]["arxiv"]
        self.timeout = timeout if timeout is not None else int(cfg["timeout_seconds"])
        self.default_query = default_query or str(cfg["default_query"])
        self.default_search_limit = (
            default_search_limit if default_search_limit is not None else int(cfg["default_search_limit"])
        )
        self.max_results_multiplier = (
            max_results_multiplier if max_results_multiplier is not None else int(cfg["max_results_multiplier"])
        )
        self.download_chunk_size = (
            download_chunk_size if download_chunk_size is not None else int(cfg["download_chunk_size"])
        )
        self.client = arxiv.Client()

    def search(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
        keywords: list[str] | None = None,
        limit: int | None = None,
        **kwargs: object,
    ) -> list[PaperMetadata]:
        """Query recent arXiv results and normalize into ``PaperMetadata`` objects."""
        resolved_limit = limit if limit is not None else self.default_search_limit
        query = str(kwargs.get("query") or "")
        category = kwargs.get("category")

        parts: list[str] = []
        if query:
            parts.append(query)
        if category:
            parts.append(f"cat:{category}")
        if keywords:
            parts.extend(f"all:{kw}" for kw in keywords)
        if not parts:
            parts.append(self.default_query)

        search = arxiv.Search(
            query=" AND ".join(parts),
            max_results=max(resolved_limit * self.max_results_multiplier, resolved_limit),
            sort_by=arxiv.SortCriterion.SubmittedDate,
        )

        start_dt = datetime.combine(start_date, time.min) if start_date else None
        end_dt = datetime.combine(end_date, time.max) if end_date else None
        if start_dt:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        if end_dt:
            end_dt = end_dt.replace(tzinfo=timezone.utc)

        papers: list[PaperMetadata] = []
        for result in self.client.results(search):
            published = _ensure_utc(result.published)
            if start_dt and published < start_dt:
                continue
            if end_dt and published > end_dt:
                continue

            # Strip version suffix so ``source_id`` stays stable across updates.
            source_id = result.get_short_id().split("v")[0]
            papers.append(
                PaperMetadata(
                    id=self._build_internal_id(source_id),
                    source=self.name,
                    source_id=source_id,
                    title=result.title.strip(),
                    authors=[author.name for author in result.authors],
                    published_at=published,
                    abstract=(result.summary or "").strip(),
                    online_url=result.entry_id,
                    pdf_url=result.pdf_url,
                    extra={"categories": result.categories},
                )
            )
            if len(papers) >= resolved_limit:
                break

        return papers

    def fetch_by_id(self, source_id: str, **kwargs: object) -> PaperMetadata | None:
        """Fetch one paper by arXiv identifier."""
        search = arxiv.Search(id_list=[source_id])
        results = list(self.client.results(search))
        if not results:
            return None

        result = results[0]
        clean_source_id = result.get_short_id().split("v")[0]
        return PaperMetadata(
            id=self._build_internal_id(clean_source_id),
            source=self.name,
            source_id=clean_source_id,
            title=result.title.strip(),
            authors=[author.name for author in result.authors],
            published_at=_ensure_utc(result.published),
            abstract=(result.summary or "").strip(),
            online_url=result.entry_id,
            pdf_url=result.pdf_url,
            extra={"categories": result.categories},
        )

    def download(self, paper: PaperMetadata, target_dir: Path, **kwargs: object) -> Path:
        """Download arXiv PDF to the target directory."""
        target_dir.mkdir(parents=True, exist_ok=True)
        pdf_url = paper.pdf_url or f"https://arxiv.org/pdf/{paper.source_id}.pdf"
        target = target_dir / f"{paper.id.replace(':', '_')}.pdf"

        with requests.get(pdf_url, stream=True, timeout=self.timeout) as response:
            response.raise_for_status()
            with target.open("wb") as fp:
                for chunk in response.iter_content(chunk_size=self.download_chunk_size):
                    if chunk:
                        fp.write(chunk)

        return target


def _ensure_utc(value: datetime) -> datetime:
    """Normalize datetime values to timezone-aware UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
