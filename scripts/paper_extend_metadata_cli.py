#!/usr/bin/env python3
"""Command line interface for ``PaperExtendMetadataService``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from service.extend_metadata import PaperExtendMetadataService
from service.extend_metadata.config import (
    DEFAULT_CONFIG_PATH,
    get_default_extend_metadata_prompt,
    get_paper_extend_metadata_config,
)
from service.fetch.config import get_paper_fetch_config
from service.fetch.paper_fetch import PaperFetch
from service.parse.config import get_paper_parse_config
from service.parse.paper_parser import PaperParser


def _resolve_config_path(argv: list[str]) -> Path:
    bootstrap = argparse.ArgumentParser(add_help=False)
    bootstrap.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    known, _ = bootstrap.parse_known_args(argv)
    return Path(known.config)


def _build_parser(config_path: str | Path) -> argparse.ArgumentParser:
    extend_cfg = get_paper_extend_metadata_config(config_path)
    fetch_cfg = get_paper_fetch_config(config_path)
    parse_cfg = get_paper_parse_config(config_path)
    openai_cfg = extend_cfg["openai"]
    parse_ollama_cfg = parse_cfg["ollama"]
    parse_pdf_cfg = parse_cfg["pdf"]

    parser = argparse.ArgumentParser(description="PaperExtendMetadataService CLI")
    parser.add_argument("--config", default=str(config_path))
    parser.add_argument("--db-path", default=extend_cfg["db_path"])
    parser.add_argument("--table-name", default=extend_cfg.get("table_name", "extend_metadata"))
    parser.add_argument("--papers-dir", default=fetch_cfg["papers_dir"])
    parser.add_argument("--parsed-dir", default=parse_cfg["parsed_dir"])
    parser.add_argument("--base-url", default=openai_cfg["base_url"])
    parser.add_argument("--api-key", default=openai_cfg.get("api_key", ""))
    parser.add_argument("--model", default=openai_cfg["model"])
    parser.add_argument("--llm-timeout", type=int, default=int(openai_cfg["timeout_seconds"]))
    parser.add_argument("--prompt", default=get_default_extend_metadata_prompt())
    parser.add_argument("--ocr-endpoint", default=parse_ollama_cfg["endpoint"])
    parser.add_argument("--ocr-model", default=parse_ollama_cfg["model"])
    parser.add_argument("--ocr-prompt", default=parse_ollama_cfg["prompt"])
    parser.add_argument("--ocr-timeout", type=int, default=int(parse_ollama_cfg["timeout_seconds"]))
    parser.add_argument("--dpi", type=int, default=int(parse_pdf_cfg["dpi"]))

    subparsers = parser.add_subparsers(dest="command", required=True)

    paper_cmd = subparsers.add_parser("paper", help="extract extend metadata for one paper")
    paper_cmd.add_argument("paper_id")
    paper_cmd.add_argument("--force-refresh", action="store_true")

    sync_cmd = subparsers.add_parser("sync", help="incrementally extract missing extend metadata")
    sync_cmd.add_argument("--force-refresh", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    config_path = _resolve_config_path(argv)
    parser = _build_parser(config_path)
    args = parser.parse_args(argv)

    fetch_service = PaperFetch(
        db_path=args.db_path,
        papers_dir=args.papers_dir,
        config_path=args.config,
    )
    parser_service = PaperParser(
        db_path=args.db_path,
        parsed_dir=args.parsed_dir,
        ollama_endpoint=args.ocr_endpoint,
        ollama_model=args.ocr_model,
        ollama_prompt=args.ocr_prompt,
        ocr_timeout=args.ocr_timeout,
        pdf_dpi=args.dpi,
        config_path=args.config,
    )
    service = PaperExtendMetadataService(
        db_path=args.db_path,
        table_name=args.table_name,
        openai_base_url=args.base_url,
        openai_api_key=args.api_key,
        openai_model=args.model,
        openai_timeout=args.llm_timeout,
        openai_prompt=args.prompt,
        config_path=args.config,
        fetch_service=fetch_service,
        parser=parser_service,
    )

    if args.command == "paper":
        payload = service.get_extended_metadata(
            args.paper_id,
            force_refresh=args.force_refresh,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    result = service.sync_incremental(
        force_refresh=args.force_refresh,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
