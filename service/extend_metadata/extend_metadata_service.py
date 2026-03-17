"""Service for extracting and persisting extended paper metadata."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models.paper import PaperMetadata
from models.paper_extend_metadata import PaperExtendMetadataRecord, PaperExtendMetadataSyncResult
from service.extend_metadata.config import (
    get_default_extend_metadata_prompt,
    get_paper_extend_metadata_config,
    resolve_openai_api_key,
)
from service.extend_metadata.openai_client import OpenAIExtendMetadataClient
from service.extend_metadata.repository import PaperExtendMetadataRepository
from service.fetch.paper_fetch import PaperFetch
from service.parse.paper_parser import PaperParser

_GITHUB_RE = re.compile(r"https?://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?")


class PaperExtendMetadataService:
    """Fetch, parse and extract extend metadata for papers."""

    def __init__(
        self,
        db_path: str | Path | None = None,
        table_name: str | None = None,
        openai_base_url: str | None = None,
        openai_api_key: str | None = None,
        openai_model: str | None = None,
        openai_timeout: int | None = None,
        openai_prompt: str | None = None,
        config_path: str | Path | None = None,
        fetch_service: PaperFetch | None = None,
        parser: PaperParser | None = None,
        llm_client: OpenAIExtendMetadataClient | None = None,
        repository: PaperExtendMetadataRepository | None = None,
    ) -> None:
        cfg = get_paper_extend_metadata_config(config_path)
        openai_cfg = _as_mapping(cfg.get("openai"), "paper_extend_metadata.openai")

        self.db_path = Path(db_path or _as_str(cfg.get("db_path"), "paper_extend_metadata.db_path"))
        self.table_name = table_name or _as_str(
            cfg.get("table_name"), "paper_extend_metadata.table_name"
        )
        self.openai_base_url = openai_base_url or _as_str(
            openai_cfg.get("base_url"), "paper_extend_metadata.openai.base_url"
        )
        self.openai_api_key = resolve_openai_api_key(
            openai_api_key if openai_api_key is not None else str(openai_cfg.get("api_key") or ""),
            config_path=config_path,
        )
        self.openai_model = openai_model or _as_str(
            openai_cfg.get("model"), "paper_extend_metadata.openai.model"
        )
        self.openai_timeout = (
            openai_timeout
            if openai_timeout is not None
            else _as_int(openai_cfg.get("timeout_seconds"), "paper_extend_metadata.openai.timeout_seconds")
        )
        self.openai_prompt = (openai_prompt or get_default_extend_metadata_prompt()).strip()

        self.repo = repository or PaperExtendMetadataRepository(
            self.db_path,
            table_name=self.table_name,
        )
        self.fetch_service = fetch_service or PaperFetch(
            db_path=self.db_path,
            config_path=config_path,
        )
        self.parser = parser or PaperParser(
            db_path=self.db_path,
            config_path=config_path,
        )
        self.llm_client = llm_client or OpenAIExtendMetadataClient(
            base_url=self.openai_base_url,
            api_key=self.openai_api_key,
            model=self.openai_model,
            timeout_seconds=self.openai_timeout,
            prompt=self.openai_prompt,
        )

    def get_extended_metadata(self, paper_id: str, *, force_refresh: bool = False) -> dict[str, Any]:
        """Return one paper's extend metadata, extracting and persisting if needed."""
        if not force_refresh:
            cached = self.repo.get_record(paper_id)
            if cached is not None:
                return cached.to_dict()

        paper = self.fetch_service.download_paper(paper_id)
        pdf_path = self._ensure_local_pdf(paper)
        first_page_text = self.parser.parse_pdf_first_page(pdf_path)
        raw_payload = self.llm_client.extract(
            paper=paper,
            first_page_text=first_page_text,
        )
        record = self._build_record(
            paper_id=paper.id,
            raw_payload=raw_payload,
            first_page_text=first_page_text,
        )
        self.repo.upsert_record(record)
        return record.to_dict()

    def get_record(self, paper_id: str) -> PaperExtendMetadataRecord | None:
        return self.repo.get_record(paper_id)

    def sync_incremental(
        self,
        *,
        limit: int | None = None,
        force_refresh: bool = False,
    ) -> PaperExtendMetadataSyncResult:
        """Extract extend metadata for papers that do not have records yet."""
        papers = self.repo.list_papers_for_extension(limit=limit)
        if not papers:
            return PaperExtendMetadataSyncResult(
                synced_at=_utc_now(),
                max_fetched_at=self.repo.get_max_papers_fetched_at(),
                processed_paper_count=0,
                failed_paper_count=0,
                llm_model=self.openai_model,
            )

        failures: list[dict[str, str]] = []
        processed = 0
        for paper in papers:
            try:
                self.get_extended_metadata(paper.id, force_refresh=force_refresh)
                processed += 1
            except Exception as exc:  # noqa: BLE001
                failures.append({"paper_id": paper.id, "error": str(exc)})

        return PaperExtendMetadataSyncResult(
            synced_at=_utc_now(),
            max_fetched_at=papers[-1].fetched_at,
            processed_paper_count=processed,
            failed_paper_count=len(failures),
            llm_model=self.openai_model,
            failures=failures,
        )

    def _ensure_local_pdf(self, paper: PaperMetadata) -> Path:
        if paper.local_pdf_path:
            pdf_path = Path(paper.local_pdf_path).expanduser().resolve()
            if pdf_path.exists():
                return pdf_path

        refreshed = self.fetch_service.download_paper(paper.id, force_refresh=True)
        if not refreshed.local_pdf_path:
            raise FileNotFoundError(f"Paper PDF was not downloaded successfully: {paper.id}")

        pdf_path = Path(refreshed.local_pdf_path).expanduser().resolve()
        if not pdf_path.exists():
            raise FileNotFoundError(f"Paper PDF file does not exist: {pdf_path}")
        return pdf_path

    def _build_record(
        self,
        *,
        paper_id: str,
        raw_payload: dict[str, Any],
        first_page_text: str,
    ) -> PaperExtendMetadataRecord:
        github_repo = _normalize_github_repo(raw_payload.get("github_repo"))
        if not github_repo:
            matched = _GITHUB_RE.search(first_page_text)
            github_repo = matched.group(0) if matched else ""

        affliations = raw_payload.get("affliations")
        if affliations is None:
            affliations = raw_payload.get("affiliations")

        return PaperExtendMetadataRecord(
            paper_id=paper_id,
            abstract_cn=str(raw_payload.get("abstract_cn") or "").strip(),
            affliations=_normalize_list(affliations),
            keywords=_normalize_list(raw_payload.get("keywords")),
            github_repo=github_repo,
            extracted_at=_utc_now(),
        )


def _normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        normalized = (
            text.replace("；", "\n")
            .replace(";", "\n")
            .replace("、", "\n")
            .replace(",", "\n")
        )
        items = [item.strip() for item in normalized.split("\n")]
    elif isinstance(value, (list, tuple, set)):
        items = [str(item).strip() for item in value]
    else:
        items = [str(value).strip()]

    deduped: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not item:
            continue
        marker = item.lower()
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(item)
    return deduped


def _normalize_github_repo(value: Any) -> str:
    if value is None:
        return ""
    raw = str(value).strip()
    if not raw:
        return ""
    matched = _GITHUB_RE.search(raw)
    return matched.group(0).rstrip("/") if matched else raw.rstrip("/")


def _as_mapping(value: Any, key_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Config '{key_name}' must be a mapping")
    return value


def _as_str(value: Any, key_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Config '{key_name}' must be a non-empty string")
    return value


def _as_int(value: Any, key_name: str) -> int:
    if not isinstance(value, int):
        raise ValueError(f"Config '{key_name}' must be an integer")
    return value


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
