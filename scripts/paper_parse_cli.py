#!/usr/bin/env python3
"""Command line interface for ``PaperParser``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from service.parse.config import DEFAULT_CONFIG_PATH, get_paper_parse_config
from service.parse.paper_parser import PaperParser


def _resolve_config_path(argv: list[str]) -> Path:
    bootstrap = argparse.ArgumentParser(add_help=False)
    bootstrap.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    known, _ = bootstrap.parse_known_args(argv)
    return Path(known.config)


def _build_parser(config_path: str | Path) -> argparse.ArgumentParser:
    cfg = get_paper_parse_config(config_path)
    pdf_cfg = cfg["pdf"]
    ollama_cfg = cfg["ollama"]

    parser = argparse.ArgumentParser(description="PaperParser CLI")
    parser.add_argument("--config", default=str(config_path))
    parser.add_argument("--db-path", default=cfg["db_path"])
    parser.add_argument("--parsed-dir", default=cfg["parsed_dir"])
    parser.add_argument("--endpoint", default=ollama_cfg["endpoint"])
    parser.add_argument("--model", default=ollama_cfg["model"])
    parser.add_argument("--prompt", default=ollama_cfg["prompt"])
    parser.add_argument("--timeout", type=int, default=ollama_cfg["timeout_seconds"])
    parser.add_argument("--dpi", type=int, default=pdf_cfg["dpi"])

    subparsers = parser.add_subparsers(dest="command", required=True)

    image_cmd = subparsers.add_parser("image", help="OCR parse local image path or base64")
    image_cmd.add_argument("--image", action="append", required=True, help="repeatable image input")

    pdf_cmd = subparsers.add_parser("pdf", help="OCR parse local PDF path")
    pdf_cmd.add_argument("--pdf", action="append", required=True, help="repeatable PDF path")

    paper_cmd = subparsers.add_parser("paper", help="parse paper by sqlite paper id")
    paper_cmd.add_argument("paper_id")

    return parser


def main(argv: list[str] | None = None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    config_path = _resolve_config_path(argv)
    parser = _build_parser(config_path)
    args = parser.parse_args(argv)

    service = PaperParser(
        db_path=args.db_path,
        parsed_dir=args.parsed_dir,
        ollama_endpoint=args.endpoint,
        ollama_model=args.model,
        ollama_prompt=args.prompt,
        ocr_timeout=args.timeout,
        pdf_dpi=args.dpi,
        config_path=args.config,
    )

    if args.command == "image":
        result = service.parse_images(args.image if len(args.image) > 1 else args.image[0])
        texts = result if isinstance(result, list) else [result]
        print(json.dumps({"texts": texts}, ensure_ascii=False, indent=2))
        return

    if args.command == "pdf":
        result = service.parse_pdfs(args.pdf if len(args.pdf) > 1 else args.pdf[0])
        texts = result if isinstance(result, list) else [result]
        print(json.dumps({"texts": texts}, ensure_ascii=False, indent=2))
        return

    path = service.parse_paper(args.paper_id)
    record = service.get_parse_record(args.paper_id)
    payload = {
        "paper_id": args.paper_id,
        "local_text_path": path,
        "status": record.status if record else "unknown",
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
