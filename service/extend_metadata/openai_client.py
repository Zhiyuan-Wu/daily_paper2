"""OpenAI chat client wrapper for paper extend metadata extraction."""

from __future__ import annotations

import json
import re
from typing import Any

from models.paper import PaperMetadata
from service.extend_metadata.config import get_default_extend_metadata_prompt

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - dependency availability varies by environment
    OpenAI = None  # type: ignore[assignment]

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.DOTALL)


class OpenAIExtendMetadataClient:
    """Extract structured paper metadata via OpenAI chat completions."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        model: str,
        timeout_seconds: int,
        prompt: str | None = None,
    ) -> None:
        if OpenAI is None:
            raise RuntimeError("Missing dependency 'openai'. Install with: pip install openai")

        self.base_url = base_url
        self.api_key = (api_key or "test-key").strip()
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.prompt = (prompt or get_default_extend_metadata_prompt()).strip()
        self.client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=self.timeout_seconds,
        )

    def extract(
        self,
        *,
        paper: PaperMetadata,
        first_page_text: str,
    ) -> dict[str, Any]:
        """Call OpenAI chat completions and parse JSON response."""
        messages = [
            {"role": "system", "content": self.prompt},
            {
                "role": "user",
                "content": _build_user_prompt(paper=paper, first_page_text=first_page_text),
            },
        ]

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0,
            response_format={"type": "json_object"},
        )

        if not response.choices:
            raise RuntimeError("OpenAI chat completion returned no choices")

        message = response.choices[0].message
        content = _extract_message_text(message.content)
        if not content.strip():
            raise RuntimeError("OpenAI chat completion returned empty content")
        return _parse_json_payload(content)


def _build_user_prompt(*, paper: PaperMetadata, first_page_text: str) -> str:
    extra = json.dumps(paper.extra or {}, ensure_ascii=False, indent=2)
    authors = ", ".join([author for author in paper.authors if author.strip()])
    published_at = paper.published_at.isoformat() if paper.published_at else ""
    return f"""
paper_id: {paper.id}
title: {paper.title}
authors: {authors}
published_at: {published_at}
online_url: {paper.online_url}
pdf_url: {paper.pdf_url or ""}
original_abstract:
{paper.abstract or ""}

extra_metadata_json:
{extra}

first_page_ocr_text:
{first_page_text}
""".strip()


def _extract_message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return str(content or "")


def _parse_json_payload(content: str) -> dict[str, Any]:
    raw = content.strip()
    matched = _JSON_BLOCK_RE.fullmatch(raw)
    if matched:
        raw = matched.group(1).strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"OpenAI did not return valid JSON: {content}") from exc

    if not isinstance(parsed, dict):
        raise RuntimeError("OpenAI JSON payload must be an object")
    return parsed
