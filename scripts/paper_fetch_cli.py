#!/usr/bin/env python3
"""Command line interface for ``PaperFetch``."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models.paper import PaperMetadata
from service.fetch.config import DEFAULT_CONFIG_PATH, get_paper_fetch_config
from service.fetch.paper_fetch import PaperFetch


def parse_kv_pairs(values: list[str] | None) -> dict[str, object]:
    """Parse repeated ``key=value`` CLI entries into dict."""
    result: dict[str, object] = {}
    if not values:
        return result

    for value in values:
        if "=" not in value:
            raise ValueError(f"Invalid --extra format: {value}. expected key=value")

        key, raw = value.split("=", 1)
        key = key.strip()
        raw = raw.strip()

        # Parse simple scalar types so plugin kwargs are easier to pass.
        if raw.lower() in {"true", "false"}:
            result[key] = raw.lower() == "true"
            continue
        try:
            result[key] = int(raw)
            continue
        except ValueError:
            pass
        result[key] = raw

    return result


def metadata_to_dict(paper: PaperMetadata) -> dict[str, Any]:
    """Convert ``PaperMetadata`` to JSON-serializable dict."""
    data = asdict(paper)
    for key in ["published_at", "fetched_at", "last_accessed_at", "downloaded_at"]:
        value = data.get(key)
        if isinstance(value, datetime):
            data[key] = value.isoformat()
    return data


def _build_parser(config_path: str | Path) -> argparse.ArgumentParser:
    """Build parser using config-driven defaults."""
    cfg = get_paper_fetch_config(config_path)
    source_cfg = cfg["sources"]
    cli_cfg = cfg["cli"]

    parser = argparse.ArgumentParser(description="PaperFetch CLI")
    parser.add_argument("--config", default=str(config_path), help="path to config.yaml")
    parser.add_argument("--db-path", default=cfg["db_path"])
    parser.add_argument("--papers-dir", default=cfg["papers_dir"])
    parser.add_argument("--max-downloaded", type=int, default=cfg["max_downloaded_papers"])
    parser.add_argument("--hf-proxy", default=source_cfg["huggingface"]["proxy_url"])

    subparsers = parser.add_subparsers(dest="command", required=True)

    search_online = subparsers.add_parser("search-online", help="query online papers")
    search_online.add_argument("--source", required=True, choices=["arxiv", "huggingface"])
    search_online.add_argument("--start-date", default=None)
    search_online.add_argument("--end-date", default=None)
    search_online.add_argument("--keywords", default=None, help="comma-separated keywords")
    search_online.add_argument("--limit", type=int, default=cli_cfg["default_online_limit"])
    search_online.add_argument("--extra", action="append", help="source extra field key=value")

    download = subparsers.add_parser("download", help="download a paper PDF")
    download.add_argument("paper_id", help="internal id (e.g. arxiv:2501.00001) or source id")
    download.add_argument("--source", default=None, help="required when paper_id is source id")
    download.add_argument("--target-dir", default=None)
    download.add_argument(
        "--force-refresh",
        action="store_true",
        help="ignore local cache and force re-download",
    )
    download.add_argument("--extra", action="append", help="download extra field key=value")

    search_local = subparsers.add_parser("search-local", help="query local metadata")
    search_local.add_argument("--source", default=None)
    search_local.add_argument("--start-date", default=None)
    search_local.add_argument("--end-date", default=None)
    search_local.add_argument("--keywords", default=None, help="comma-separated keywords")
    search_local.add_argument("--has-pdf", choices=["true", "false"], default=None)
    search_local.add_argument("--limit", type=int, default=cli_cfg["default_local_limit"])

    return parser


def _resolve_config_path(argv: list[str]) -> Path:
    """Resolve config path from CLI args before building full parser."""
    bootstrap = argparse.ArgumentParser(add_help=False)
    bootstrap.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    known, _ = bootstrap.parse_known_args(argv)
    return Path(known.config)


def main(argv: list[str] | None = None) -> None:
    """Run CLI entrypoint."""
    argv = argv if argv is not None else sys.argv[1:]
    config_path = _resolve_config_path(argv)
    parser = _build_parser(config_path)
    args = parser.parse_args(argv)

    fetch = PaperFetch(
        db_path=args.db_path,
        papers_dir=args.papers_dir,
        max_downloaded_papers=args.max_downloaded,
        hf_proxy_url=args.hf_proxy,
        config_path=args.config,
    )

    if args.command == "search-online":
        extra = parse_kv_pairs(args.extra)
        papers = fetch.search_online(
            source=args.source,
            start_date=args.start_date,
            end_date=args.end_date,
            keywords=args.keywords,
            limit=args.limit,
            **extra,
        )
        print(json.dumps([metadata_to_dict(p) for p in papers], ensure_ascii=False, indent=2))
        return

    if args.command == "download":
        extra = parse_kv_pairs(args.extra)
        paper = fetch.download_paper(
            paper_id=args.paper_id,
            source=args.source,
            target_dir=args.target_dir,
            force_refresh=args.force_refresh,
            **extra,
        )
        print(json.dumps(metadata_to_dict(paper), ensure_ascii=False, indent=2))
        return

    has_pdf = None
    if args.has_pdf == "true":
        has_pdf = True
    elif args.has_pdf == "false":
        has_pdf = False

    papers = fetch.query_local(
        source=args.source,
        start_date=args.start_date,
        end_date=args.end_date,
        keywords=args.keywords,
        has_pdf=has_pdf,
        limit=args.limit,
    )
    print(json.dumps([metadata_to_dict(p) for p in papers], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
