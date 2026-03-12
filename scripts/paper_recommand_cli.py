#!/usr/bin/env python3
"""Command line interface for ``PaperRecommandService``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from service.recommand import PaperRecommandService
from service.recommand.config import DEFAULT_CONFIG_PATH, get_paper_recommand_config


def _resolve_config_path(argv: list[str]) -> Path:
    bootstrap = argparse.ArgumentParser(add_help=False)
    bootstrap.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    known, _ = bootstrap.parse_known_args(argv)
    return Path(known.config)


def _build_parser(config_path: str | Path) -> argparse.ArgumentParser:
    cfg = get_paper_recommand_config(config_path)

    parser = argparse.ArgumentParser(description="PaperRecommandService CLI")
    parser.add_argument("--config", default=str(config_path))
    parser.add_argument("--db-path", default=cfg["db_path"])
    parser.add_argument("--paper-table", default=cfg.get("paper_table", "papers"))
    parser.add_argument("--activity-table", default=cfg.get("activity_table", "activity"))
    parser.add_argument("--default-algorithm", default=cfg.get("default_algorithm", "fusion"))
    parser.add_argument("--default-top-k", type=int, default=int(cfg.get("default_top_k", 20)))

    subparsers = parser.add_subparsers(dest="command", required=True)

    recommend_cmd = subparsers.add_parser("recommend", help="run recommendation")
    recommend_cmd.add_argument("--algorithm", default=None)
    recommend_cmd.add_argument("--query", default="")
    recommend_cmd.add_argument("--top-k", type=int, default=None)
    recommend_cmd.add_argument("--now", default=None, help="ISO datetime/date for time plugin")

    subparsers.add_parser("algorithms", help="list available algorithms")
    return parser


def main(argv: list[str] | None = None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    config_path = _resolve_config_path(argv)
    parser = _build_parser(config_path)
    args = parser.parse_args(argv)

    service = PaperRecommandService(
        db_path=args.db_path,
        paper_table=args.paper_table,
        activity_table=args.activity_table,
        default_algorithm=args.default_algorithm,
        default_top_k=args.default_top_k,
        config_path=args.config,
    )

    if args.command == "algorithms":
        print(json.dumps({"algorithms": service.list_algorithms()}, ensure_ascii=False, indent=2))
        return

    results = service.recommend(
        algorithm=args.algorithm,
        query=args.query,
        top_k=args.top_k,
        now=args.now,
    )
    payload = {
        "algorithm": (args.algorithm or service.default_algorithm).lower(),
        "query": args.query,
        "count": len(results),
        "results": [row.to_dict() for row in results],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
