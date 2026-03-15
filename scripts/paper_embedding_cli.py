#!/usr/bin/env python3
"""Command line interface for ``PaperEmbeddingService``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from service.embedding.config import DEFAULT_CONFIG_PATH, get_paper_embedding_config
from service.embedding.embedding_service import PaperEmbeddingService


def _resolve_config_path(argv: list[str]) -> Path:
    bootstrap = argparse.ArgumentParser(add_help=False)
    bootstrap.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    known, _ = bootstrap.parse_known_args(argv)
    return Path(known.config)


def _build_parser(config_path: str | Path) -> argparse.ArgumentParser:
    cfg = get_paper_embedding_config(config_path)
    ollama_cfg = _as_mapping(cfg.get("ollama"), "paper_embedding.ollama")

    parser = argparse.ArgumentParser(description="PaperEmbeddingService CLI")
    parser.add_argument("--config", default=str(config_path))
    parser.add_argument("--db-path", default=cfg["db_path"])
    parser.add_argument("--embedding-table", default=cfg.get("embedding_table", "paper_embeddings"))
    parser.add_argument("--endpoint", default=ollama_cfg["endpoint"])
    parser.add_argument("--model", default=ollama_cfg["model"])
    parser.add_argument("--timeout", type=int, default=int(ollama_cfg["timeout_seconds"]))
    parser.add_argument("--top-k", type=int, default=int(cfg.get("default_top_k", 5)))
    parser.add_argument("--batch-size", type=int, default=int(cfg.get("default_batch_size", 8)))

    subparsers = parser.add_subparsers(dest="command", required=True)

    sync_cmd = subparsers.add_parser("sync", help="sync paper embeddings incrementally")
    sync_cmd.add_argument("--batch-size", type=int)
    sync_cmd.add_argument("--force-full", action="store_true")

    search_cmd = subparsers.add_parser("search", help="semantic search papers")
    search_cmd.add_argument("query")
    search_cmd.add_argument("--top-k", type=int)
    search_cmd.add_argument("--published-from")
    search_cmd.add_argument("--published-to")
    search_cmd.add_argument("--fetched-from")
    search_cmd.add_argument("--fetched-to")

    embed_cmd = subparsers.add_parser("embed", help="embed one or more texts")
    embed_cmd.add_argument("--text", action="append", required=True)
    embed_cmd.add_argument("--batch-size", type=int)

    return parser


def main(argv: list[str] | None = None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    config_path = _resolve_config_path(argv)
    parser = _build_parser(config_path)
    args = parser.parse_args(argv)

    service = PaperEmbeddingService(
        db_path=args.db_path,
        embedding_table=args.embedding_table,
        ollama_endpoint=args.endpoint,
        ollama_model=args.model,
        ollama_timeout=args.timeout,
        default_top_k=args.top_k,
        default_batch_size=args.batch_size,
        config_path=args.config,
    )

    if args.command == "sync":
        version = service.sync_incremental(
            batch_size=args.batch_size,
            force_full=args.force_full,
        )
        print(json.dumps(version.to_dict(), ensure_ascii=False, indent=2))
        return

    if args.command == "search":
        hits = service.search(
            args.query,
            top_k=args.top_k,
            published_from=args.published_from,
            published_to=args.published_to,
            fetched_from=args.fetched_from,
            fetched_to=args.fetched_to,
        )
        print(
            json.dumps(
                {
                    "query": args.query,
                    "count": len(hits),
                    "hits": [service.hit_to_dict(hit) for hit in hits],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    vectors = service.embed_texts(args.text, batch_size=args.batch_size)
    print(json.dumps({"texts": args.text, "embeddings": vectors}, ensure_ascii=False, indent=2))


def _as_mapping(value: Any, key_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Config '{key_name}' must be a mapping")
    return value


if __name__ == "__main__":
    main()
