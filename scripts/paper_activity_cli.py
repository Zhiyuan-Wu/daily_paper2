#!/usr/bin/env python3
"""Command line interface for ``PaperActivityManager``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from service.activity_management.activity_manager import PaperActivityManager
from service.activity_management.config import DEFAULT_CONFIG_PATH, get_paper_activity_config


def _resolve_config_path(argv: list[str]) -> Path:
    bootstrap = argparse.ArgumentParser(add_help=False)
    bootstrap.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    known, _ = bootstrap.parse_known_args(argv)
    return Path(known.config)


def _build_parser(config_path: str | Path) -> argparse.ArgumentParser:
    cfg = get_paper_activity_config(config_path)
    cli_cfg = _as_mapping(cfg.get("cli"), "paper_activity.cli")

    parser = argparse.ArgumentParser(description="PaperActivityManager CLI")
    parser.add_argument("--config", default=str(config_path))
    parser.add_argument("--db-path", default=cfg["db_path"])
    parser.add_argument("--table-name", default=cfg.get("table_name", "activity"))

    subparsers = parser.add_subparsers(dest="command", required=True)

    create_cmd = subparsers.add_parser("create", help="create one activity row")
    create_cmd.add_argument("paper_id")
    create_cmd.add_argument("--recommendation-time", action="append", default=[])
    create_cmd.add_argument("--user-notes", default="")
    create_cmd.add_argument("--ai-report-summary", default="")
    create_cmd.add_argument("--ai-report-path", default="")
    create_cmd.add_argument("--like", type=int, choices=[-1, 0, 1], default=0)
    create_cmd.add_argument("--overwrite", action="store_true")

    get_cmd = subparsers.add_parser("get", help="get one activity row")
    get_cmd.add_argument("paper_id")

    list_cmd = subparsers.add_parser("list", help="list activity rows")
    list_cmd.add_argument("--limit", type=int, default=int(cli_cfg.get("default_limit", 100)))
    list_cmd.add_argument("--offset", type=int, default=0)

    update_cmd = subparsers.add_parser("update", help="update one activity row")
    update_cmd.add_argument("paper_id")
    update_cmd.add_argument("--recommendation-time", action="append")
    update_cmd.add_argument("--user-notes")
    update_cmd.add_argument("--ai-report-summary")
    update_cmd.add_argument("--ai-report-path")
    update_cmd.add_argument("--like", type=int, choices=[-1, 0, 1])

    append_cmd = subparsers.add_parser(
        "append-recommendation",
        help="append recommendation timestamp for one paper",
    )
    append_cmd.add_argument("paper_id")
    append_cmd.add_argument("recommendation_time")

    delete_cmd = subparsers.add_parser("delete", help="delete one activity row")
    delete_cmd.add_argument("paper_id")

    return parser


def main(argv: list[str] | None = None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    config_path = _resolve_config_path(argv)
    parser = _build_parser(config_path)
    args = parser.parse_args(argv)

    manager = PaperActivityManager(
        db_path=args.db_path,
        table_name=args.table_name,
        config_path=args.config,
    )

    if args.command == "create":
        created = manager.create_activity(
            args.paper_id,
            recommendation_records=args.recommendation_time,
            user_notes=args.user_notes,
            ai_report_summary=args.ai_report_summary,
            ai_report_path=args.ai_report_path,
            like=args.like,
            overwrite=args.overwrite,
        )
        print(json.dumps(manager.to_dict(created), ensure_ascii=False, indent=2))
        return

    if args.command == "get":
        record = manager.get_activity(args.paper_id)
        payload = manager.to_dict(record) if record else None
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if args.command == "list":
        rows = manager.list_activities(limit=args.limit, offset=args.offset)
        print(json.dumps([manager.to_dict(row) for row in rows], ensure_ascii=False, indent=2))
        return

    if args.command == "update":
        updated = manager.update_activity(
            args.paper_id,
            recommendation_records=args.recommendation_time,
            user_notes=args.user_notes,
            ai_report_summary=args.ai_report_summary,
            ai_report_path=args.ai_report_path,
            like=args.like,
        )
        print(json.dumps(manager.to_dict(updated), ensure_ascii=False, indent=2))
        return

    if args.command == "append-recommendation":
        updated = manager.append_recommendation(args.paper_id, args.recommendation_time)
        print(json.dumps(manager.to_dict(updated), ensure_ascii=False, indent=2))
        return

    deleted = manager.delete_activity(args.paper_id)
    print(json.dumps({"paper_id": args.paper_id, "deleted": deleted}, ensure_ascii=False, indent=2))


def _as_mapping(value: Any, key_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Config '{key_name}' must be a mapping")
    return value


if __name__ == "__main__":
    main()
