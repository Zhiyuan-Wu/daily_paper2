"""Hugging Face Daily Papers source plugin."""

from __future__ import annotations

import html
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from models.paper import PaperMetadata
from service.fetch.config import get_paper_fetch_config
from service.fetch.sources.base import PaperSource

_ARXIV_ID_PATTERN = re.compile(r"^\d{4}\.\d{4,5}(v\d+)?$")


class HuggingFacePaperSource(PaperSource):
    """Fetch metadata from Hugging Face daily papers pages.

    The plugin parses ``data-target=DailyPapers`` and ``data-target=PaperPage`` payloads
    embedded in HTML, then converts records to the shared ``PaperMetadata`` schema.
    """

    name = "huggingface"

    def __init__(
        self,
        proxy_url: str | None = None,
        timeout: int | None = None,
        use_proxy: bool | None = None,
        download_chunk_size: int | None = None,
        default_search_limit: int | None = None,
        config_path: str | Path | None = None,
    ) -> None:
        """Initialize HuggingFace source with config-driven defaults."""
        cfg = get_paper_fetch_config(config_path)["sources"]["huggingface"]
        self.proxy_url = proxy_url or str(cfg["proxy_url"])
        self.timeout = timeout if timeout is not None else int(cfg["timeout_seconds"])
        self.use_proxy = use_proxy if use_proxy is not None else bool(cfg["use_proxy"])
        self.download_chunk_size = (
            download_chunk_size if download_chunk_size is not None else int(cfg["download_chunk_size"])
        )
        self.default_search_limit = (
            default_search_limit if default_search_limit is not None else int(cfg["default_search_limit"])
        )

    def search(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
        keywords: list[str] | None = None,
        limit: int | None = None,
        **kwargs: object,
    ) -> list[PaperMetadata]:
        """Search papers by date range and keyword filters."""
        resolved_limit = limit if limit is not None else self.default_search_limit
        if resolved_limit < 1:
            raise ValueError("limit must be greater than or equal to 1")
        start = start_date or end_date or date.today()
        end = end_date or start
        if start > end:
            start, end = end, start

        proxy_url = kwargs.get("proxy_url") if "proxy_url" in kwargs else self.proxy_url
        use_proxy = bool(kwargs.get("use_proxy", self.use_proxy))

        papers: list[PaperMetadata] = []
        for day in self._iter_dates(start, end):
            payload = self._fetch_daily_payload(day, proxy_url=proxy_url, use_proxy=use_proxy)
            for item in payload.get("dailyPapers", []):
                paper = item.get("paper") or {}
                source_id = str(paper.get("id") or "").strip()
                if not source_id:
                    continue

                title = str(item.get("title") or paper.get("title") or "").strip()
                summary = str(item.get("summary") or paper.get("summary") or "").strip()
                if keywords and not self._match_keywords(title, summary, keywords):
                    continue

                authors = [author.get("name", "") for author in paper.get("authors", []) if author.get("name")]
                published_at = _parse_iso_datetime(str(paper.get("publishedAt") or item.get("publishedAt") or ""))
                online_url = f"https://huggingface.co/papers/{source_id}"

                pdf_url: str | None = None
                if _ARXIV_ID_PATTERN.match(source_id):
                    # Most daily papers map to arXiv ids, so we can infer a stable PDF link.
                    pdf_url = f"https://arxiv.org/pdf/{source_id}.pdf"

                papers.append(
                    PaperMetadata(
                        id=self._build_internal_id(source_id),
                        source=self.name,
                        source_id=source_id,
                        title=title,
                        authors=authors,
                        published_at=published_at,
                        abstract=summary,
                        online_url=online_url,
                        pdf_url=pdf_url,
                        extra={
                            "hf_date": day.isoformat(),
                            "upvotes": paper.get("upvotes"),
                            "github_repo": paper.get("githubRepo"),
                            "organization": (paper.get("organization") or {}).get("name"),
                        },
                    )
                )
                if len(papers) >= resolved_limit:
                    return papers

        return papers

    def fetch_by_id(self, source_id: str, **kwargs: object) -> PaperMetadata | None:
        """Fetch a single paper metadata from ``/papers/{id}`` page."""
        proxy_url = kwargs.get("proxy_url") if "proxy_url" in kwargs else self.proxy_url
        use_proxy = bool(kwargs.get("use_proxy", self.use_proxy))

        page_url = f"https://huggingface.co/papers/{source_id}"
        response = requests.get(
            page_url,
            timeout=self.timeout,
            **self._requests_proxy_kwargs(proxy_url=proxy_url, use_proxy=use_proxy),
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        paper_payload = self._extract_paper_payload(soup)
        if not paper_payload:
            return None

        title = str(paper_payload.get("title") or "").strip()
        summary = str(paper_payload.get("summary") or "").strip()
        authors = [author.get("name", "") for author in paper_payload.get("authors", []) if author.get("name")]
        published_at = _parse_iso_datetime(str(paper_payload.get("publishedAt") or ""))
        pdf_url = self._extract_pdf_url(soup, source_id)

        return PaperMetadata(
            id=self._build_internal_id(source_id),
            source=self.name,
            source_id=source_id,
            title=title,
            authors=authors,
            published_at=published_at,
            abstract=summary,
            online_url=page_url,
            pdf_url=pdf_url,
            extra={
                "upvotes": paper_payload.get("upvotes"),
                "github_repo": paper_payload.get("githubRepo"),
                "organization": (paper_payload.get("organization") or {}).get("name"),
            },
        )

    def download(self, paper: PaperMetadata, target_dir: Path, **kwargs: object) -> Path:
        """Download paper PDF, resolving URL from paper page when needed."""
        proxy_url = kwargs.get("proxy_url") if "proxy_url" in kwargs else self.proxy_url
        use_proxy = bool(kwargs.get("use_proxy", self.use_proxy))

        pdf_url = paper.pdf_url
        if not pdf_url:
            pdf_url = self._resolve_pdf_url(paper.source_id, proxy_url=proxy_url, use_proxy=use_proxy)
        if not pdf_url:
            raise ValueError(f"No downloadable PDF URL found for {paper.source_id}")

        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{paper.id.replace(':', '_')}.pdf"

        with requests.get(
            pdf_url,
            stream=True,
            timeout=self.timeout,
            **self._requests_proxy_kwargs(proxy_url=proxy_url, use_proxy=use_proxy),
        ) as response:
            response.raise_for_status()
            with target_path.open("wb") as fp:
                for chunk in response.iter_content(chunk_size=self.download_chunk_size):
                    if chunk:
                        fp.write(chunk)

        return target_path

    def _fetch_daily_payload(self, day: date, proxy_url: str | None, use_proxy: bool) -> dict:
        """Fetch one daily page and decode JSON payload embedded in HTML attributes."""
        url = f"https://huggingface.co/papers/date/{day.isoformat()}"
        response = requests.get(
            url,
            timeout=self.timeout,
            **self._requests_proxy_kwargs(proxy_url=proxy_url, use_proxy=use_proxy),
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        node = soup.find(attrs={"data-target": "DailyPapers"})
        if not node:
            return {}

        raw_props = node.get("data-props")
        if not raw_props:
            return {}

        return json.loads(html.unescape(raw_props))

    def _extract_paper_payload(self, soup: BeautifulSoup) -> dict:
        """Extract single-paper payload from detail page."""
        node = soup.find(attrs={"data-target": "PaperPage"})
        if not node:
            return {}
        raw_props = node.get("data-props")
        if not raw_props:
            return {}
        payload = json.loads(html.unescape(raw_props))
        return payload.get("paper") or {}

    def _resolve_pdf_url(self, source_id: str, proxy_url: str | None, use_proxy: bool) -> str | None:
        """Resolve PDF URL by parsing paper detail page links."""
        page_url = f"https://huggingface.co/papers/{source_id}"
        response = requests.get(
            page_url,
            timeout=self.timeout,
            **self._requests_proxy_kwargs(proxy_url=proxy_url, use_proxy=use_proxy),
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        return self._extract_pdf_url(soup, source_id)

    def _extract_pdf_url(self, soup: BeautifulSoup, source_id: str) -> str | None:
        """Extract first viable PDF URL from page anchors."""
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "arxiv.org/pdf/" in href:
                return href
            if href.lower().endswith(".pdf"):
                return href

        if _ARXIV_ID_PATTERN.match(source_id):
            return f"https://arxiv.org/pdf/{source_id}.pdf"
        return None

    def _requests_proxy_kwargs(self, proxy_url: str | None, use_proxy: bool) -> dict[str, object]:
        """Build optional proxy kwargs for ``requests`` calls."""
        if use_proxy and proxy_url:
            return {"proxies": {"http": proxy_url, "https": proxy_url}}
        return {}

    @staticmethod
    def _iter_dates(start: date, end: date) -> list[date]:
        """Iterate date range from new to old (descending)."""
        current = end
        values: list[date] = []
        while current >= start:
            values.append(current)
            current -= timedelta(days=1)
        return values

    @staticmethod
    def _match_keywords(title: str, summary: str, keywords: list[str]) -> bool:
        """Return ``True`` only when all keywords appear in title+summary."""
        text = f"{title}\n{summary}".lower()
        return all(keyword.lower() in text for keyword in keywords)


def _parse_iso_datetime(raw: str) -> datetime | None:
    """Parse ISO datetime into timezone-aware UTC datetime."""
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
