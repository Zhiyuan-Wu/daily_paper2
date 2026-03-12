"""Paper parsing module: image OCR, PDF OCR and paper-id pipeline."""

from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path
from typing import Any

import requests

from models.paper_parse import PaperParseRecord
from service.parse.config import get_paper_parse_config
from service.parse.repository import PaperParseRepository

ImageInput = str | Path | bytes


class PaperParser:
    """Standalone parser service with sqlite status tracking."""

    def __init__(
        self,
        db_path: str | Path | None = None,
        parsed_dir: str | Path | None = None,
        ollama_endpoint: str | None = None,
        ollama_model: str | None = None,
        ollama_prompt: str | None = None,
        ocr_timeout: int | None = None,
        pdf_dpi: int | None = None,
        config_path: str | Path | None = None,
    ) -> None:
        cfg = get_paper_parse_config(config_path)
        pdf_cfg = _as_mapping(cfg.get("pdf"), "paper_parse.pdf")
        ollama_cfg = _as_mapping(cfg.get("ollama"), "paper_parse.ollama")

        resolved_db_path = db_path or _as_str(cfg.get("db_path"), "paper_parse.db_path")
        resolved_parsed_dir = parsed_dir or _as_str(cfg.get("parsed_dir"), "paper_parse.parsed_dir")

        self.db_path = Path(resolved_db_path)
        self.parsed_dir = Path(resolved_parsed_dir)
        self.parsed_dir.mkdir(parents=True, exist_ok=True)

        self.ollama_endpoint = ollama_endpoint or _as_str(
            ollama_cfg.get("endpoint"), "paper_parse.ollama.endpoint"
        )
        self.ollama_model = ollama_model or _as_str(ollama_cfg.get("model"), "paper_parse.ollama.model")
        self.ollama_prompt = ollama_prompt or _as_str(ollama_cfg.get("prompt"), "paper_parse.ollama.prompt")
        self.ocr_timeout = (
            ocr_timeout if ocr_timeout is not None else _as_int(ollama_cfg.get("timeout_seconds"), "paper_parse.ollama.timeout_seconds")
        )
        self.pdf_dpi = pdf_dpi if pdf_dpi is not None else _as_int(pdf_cfg.get("dpi"), "paper_parse.pdf.dpi")

        self.repo = PaperParseRepository(self.db_path)

    def parse_images(self, images: ImageInput | list[ImageInput]) -> str | list[str]:
        """OCR one image or multiple images from local path/base64/bytes."""
        image_list, is_batch = _to_list(images)
        texts: list[str] = []
        for i,image in enumerate(image_list):
            print(f"Processing pages {i+1}/{len(image_list)}...")
            b64 = self._image_input_to_base64(image)
            texts.append(self._ocr_with_ollama(b64))
        return texts if is_batch else texts[0]

    def parse_pdfs(self, pdf_paths: str | Path | list[str | Path]) -> str | list[str]:
        """Parse one or multiple PDFs by converting each page into image OCR."""
        pdf_list, is_batch = _to_list(pdf_paths)
        outputs: list[str] = []
        for pdf_path in pdf_list:
            text, _ = self._parse_one_pdf(Path(pdf_path))
            outputs.append(text)
        return outputs if is_batch else outputs[0]

    def parse_paper(self, paper_id: str) -> str:
        """Parse a paper by id: db lookup -> pdf OCR -> markdown -> db status."""
        if not self.repo.paper_exists(paper_id):
            raise ValueError(f"Paper id not found in sqlite: {paper_id}")

        pdf_path_str = self.repo.get_paper_pdf_path(paper_id)
        if not pdf_path_str:
            message = f"Paper has no local_pdf_path in sqlite: {paper_id}"
            self.repo.save_parse_failure(paper_id=paper_id, error_message=message, ocr_model=self.ollama_model)
            raise ValueError(message)

        pdf_path = Path(pdf_path_str).expanduser().resolve()
        if not pdf_path.exists():
            message = f"Local PDF not found: {pdf_path}"
            self.repo.save_parse_failure(paper_id=paper_id, error_message=message, ocr_model=self.ollama_model)
            raise FileNotFoundError(message)

        out_path = self.parsed_dir / f"{paper_id.replace(':', '_')}.md"
        try:
            text, page_count = self._parse_one_pdf(pdf_path)
            out_path.write_text(text, encoding="utf-8")
            self.repo.save_parse_success(
                paper_id=paper_id,
                local_text_path=str(out_path),
                page_count=page_count,
                ocr_model=self.ollama_model,
            )
        except Exception as exc:  # noqa: BLE001
            self.repo.save_parse_failure(
                paper_id=paper_id,
                error_message=str(exc),
                ocr_model=self.ollama_model,
            )
            raise

        return str(out_path)

    def get_parse_record(self, paper_id: str) -> PaperParseRecord | None:
        """Read parse status from sqlite."""
        return self.repo.get_parse_record(paper_id)

    def _parse_one_pdf(self, pdf_path: Path) -> tuple[str, int]:
        images = self._convert_pdf_to_images(pdf_path)
        page_texts = self.parse_images(images)
        assert isinstance(page_texts, list)

        chunks: list[str] = [f"# Parsed Content: {pdf_path.name}", ""]
        for idx, content in enumerate(page_texts, start=1):
            chunks.append(f"## Page {idx}")
            chunks.append("")
            chunks.append(content.strip())
            chunks.append("")
        return "\n".join(chunks).strip() + "\n", len(page_texts)

    def _convert_pdf_to_images(self, pdf_path: Path) -> list[Any]:
        try:
            from pdf2image import convert_from_path
            from pdf2image.exceptions import PDFInfoNotInstalledError, PDFPageCountError, PDFSyntaxError
        except ImportError as exc:
            raise RuntimeError("Missing dependency 'pdf2image'. Install with: pip install pdf2image") from exc

        try:
            images = convert_from_path(str(pdf_path), dpi=self.pdf_dpi)
        except PDFInfoNotInstalledError as exc:
            raise RuntimeError(
                "Poppler is required but not found (pdftoppm missing). "
                "Install poppler and ensure 'pdftoppm' is in PATH."
            ) from exc
        except (PDFPageCountError, PDFSyntaxError) as exc:
            raise RuntimeError(f"Failed to parse PDF: {pdf_path}") from exc

        if not images:
            raise RuntimeError(f"No pages rendered from PDF: {pdf_path}")
        return images

    @staticmethod
    def _image_to_base64(image: Any) -> str:
        buf = BytesIO()
        image.save(buf, format="JPEG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    def _image_input_to_base64(self, image: Any) -> str:
        if hasattr(image, "save") and callable(image.save):
            return self._image_to_base64(image)

        if isinstance(image, bytes):
            return base64.b64encode(image).decode("utf-8")

        if isinstance(image, Path):
            if not image.exists():
                raise FileNotFoundError(f"Image file not found: {image}")
            return base64.b64encode(image.read_bytes()).decode("utf-8")

        raw = image.strip()
        path = Path(raw).expanduser()
        if path.exists() and path.is_file():
            return base64.b64encode(path.read_bytes()).decode("utf-8")

        if raw.startswith("data:image") and "," in raw:
            raw = raw.split(",", 1)[1]

        normalized = "".join(raw.split())
        try:
            # Validate base64 input before sending to model.
            base64.b64decode(normalized, validate=True)
            return normalized
        except Exception as exc:  # noqa: BLE001
            raise ValueError("Image input must be local file path, bytes, or base64 string") from exc

    def _ocr_with_ollama(self, image_base64: str) -> str:
        payload = {
            "model": self.ollama_model,
            "messages": [
                {
                    "role": "user",
                    "content": self.ollama_prompt,
                    "images": [image_base64],
                }
            ],
            "stream": False,
        }
        response = requests.post(self.ollama_endpoint, json=payload, timeout=self.ocr_timeout)
        response.raise_for_status()
        data = response.json()

        text = ((data.get("message") or {}).get("content") or "").strip()
        if text:
            return text

        # Some Ollama-compatible endpoints return ``response``.
        fallback = data.get("response")
        if isinstance(fallback, str):
            return fallback.strip()
        return ""


# Backward-compatible alias for requested class naming style.
Paper_Parser = PaperParser


def _to_list(value: Any) -> tuple[list[Any], bool]:
    if isinstance(value, (list, tuple)):
        return list(value), True
    if isinstance(value, set):
        return list(value), True
    return [value], False


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
