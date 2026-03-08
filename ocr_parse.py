#!/usr/bin/env python3
"""Parse first-page OCR text from a PDF using pdf2image + Ollama.

Workflow:
1. Convert PDF pages to a PIL image list via ``pdf2image``.
2. Pick the first page image.
3. Send image (base64) to Ollama OCR chat API.
4. Print recognized text.
"""

from __future__ import annotations

import argparse
import base64
import json
from io import BytesIO
from pathlib import Path

import requests

DEFAULT_PDF_PATH = Path(__file__).resolve().parent / "data/papers/arxiv_2603.05500.pdf"
DEFAULT_OLLAMA_ENDPOINT = "http://localhost:11434/api/chat"
DEFAULT_MODEL = "glm-ocr"
DEFAULT_PROMPT = "Text Recognition:"


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="OCR first page of a PDF via Ollama")
    parser.add_argument("--pdf", default=str(DEFAULT_PDF_PATH), help="path to PDF file")
    parser.add_argument("--dpi", type=int, default=200, help="pdf2image rendering DPI")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="ollama model name, e.g. glm-ocr")
    parser.add_argument("--endpoint", default=DEFAULT_OLLAMA_ENDPOINT, help="ollama chat API endpoint")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT, help="OCR prompt text sent to model")
    parser.add_argument("--timeout", type=int, default=120, help="HTTP timeout seconds")
    return parser.parse_args()


def convert_pdf_to_images(pdf_path: Path, dpi: int):
    """Convert PDF to a list of PIL images using pdf2image.

    Raises a readable RuntimeError when dependencies are missing.
    """
    try:
        from pdf2image import convert_from_path
        from pdf2image.exceptions import PDFInfoNotInstalledError, PDFPageCountError, PDFSyntaxError
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency 'pdf2image'. Install with: pip install pdf2image"
        ) from exc

    try:
        images = convert_from_path(str(pdf_path), dpi=dpi)
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


def image_to_base64(image) -> str:
    """Encode PIL image to base64 (JPEG)."""
    buf = BytesIO()
    image.save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def ocr_with_ollama(
    *,
    image_base64: str,
    endpoint: str,
    model: str,
    prompt: str,
    timeout: int,
) -> str:
    """Send OCR request to Ollama and return extracted text."""
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [image_base64],
            }
        ],
        "stream": False,
    }

    resp = requests.post(endpoint, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()

    # Typical Ollama chat response text is in ``message.content``.
    text = ((data.get("message") or {}).get("content") or "").strip()
    if text:
        return text


def main() -> None:
    """Run OCR parse pipeline and print recognized text."""
    args = parse_args()
    pdf_path = Path(args.pdf).expanduser().resolve()

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    images = convert_pdf_to_images(pdf_path=pdf_path, dpi=args.dpi)
    first_page_image = images[0]

    image_b64 = image_to_base64(first_page_image)
    text = ocr_with_ollama(
        image_base64=image_b64,
        endpoint=args.endpoint,
        model=args.model,
        prompt=args.prompt,
        timeout=args.timeout,
    )

    print(text)


if __name__ == "__main__":
    main()
