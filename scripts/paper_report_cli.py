#!/usr/bin/env python3
"""Command line interface for ``DailyReportManager``."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from service.report_management.config import DEFAULT_CONFIG_PATH, get_paper_report_config
from service.report_management.report_manager import DailyReportManager


def _resolve_config_path(argv: list[str]) -> Path:
    bootstrap = argparse.ArgumentParser(add_help=False)
    bootstrap.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    known, _ = bootstrap.parse_known_args(argv)
    return Path(known.config)


def _build_parser(config_path: str | Path) -> argparse.ArgumentParser:
    cfg = get_paper_report_config(config_path)
    cli_cfg = _as_mapping(cfg.get("cli"), "paper_report.cli")

    parser = argparse.ArgumentParser(description="DailyReportManager CLI")
    parser.add_argument("--config", default=str(config_path))
    parser.add_argument("--db-path", default=cfg["db_path"])
    parser.add_argument("--table-name", default=cfg.get("table_name", "report"))

    subparsers = parser.add_subparsers(dest="command", required=True)

    create_cmd = subparsers.add_parser("create", help="create one daily report row")
    create_cmd.add_argument("report_id")
    create_cmd.add_argument("--report-date", required=True, help="ISO date, e.g. 2026-03-11")
    create_cmd.add_argument(
        "--generated-at",
        default=datetime.now(timezone.utc).isoformat(),
        help="ISO datetime, e.g. 2026-03-11T08:00:00+00:00",
    )
    create_cmd.add_argument("--paper-id", action="append", default=[])
    create_cmd.add_argument("--local-md-path", default="")
    create_cmd.add_argument("--overwrite", action="store_true")

    get_cmd = subparsers.add_parser("get", help="get one daily report row")
    get_cmd.add_argument("report_id")

    list_cmd = subparsers.add_parser("list", help="list daily report rows")
    list_cmd.add_argument("--limit", type=int, default=int(cli_cfg.get("default_limit", 100)))
    list_cmd.add_argument("--offset", type=int, default=0)
    list_cmd.add_argument("--report-date", help="filter by ISO date")

    update_cmd = subparsers.add_parser("update", help="update one daily report row")
    update_cmd.add_argument("report_id")
    update_cmd.add_argument("--report-date")
    update_cmd.add_argument("--generated-at")
    update_cmd.add_argument("--paper-id", action="append")
    update_cmd.add_argument("--local-md-path")

    delete_cmd = subparsers.add_parser("delete", help="delete one daily report row")
    delete_cmd.add_argument("report_id")

    return parser


def main(argv: list[str] | None = None) -> None:
    argv = argv if argv is not None else sys.argv[1:]
    config_path = _resolve_config_path(argv)
    parser = _build_parser(config_path)
    args = parser.parse_args(argv)

    manager = DailyReportManager(
        db_path=args.db_path,
        table_name=args.table_name,
        config_path=args.config,
    )

    if args.command == "create":
        created = manager.create_report(
            args.report_id,
            report_date=args.report_date,
            generated_at=args.generated_at,
            related_paper_ids=args.paper_id,
            local_md_path=args.local_md_path,
            overwrite=args.overwrite,
        )
        print(json.dumps(manager.to_dict(created), ensure_ascii=False, indent=2))
        return

    if args.command == "get":
        record = manager.get_report(args.report_id)
        payload = manager.to_dict(record) if record else None
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if args.command == "list":
        rows = manager.list_reports(limit=args.limit, offset=args.offset, report_date=args.report_date)
        print(json.dumps([manager.to_dict(row) for row in rows], ensure_ascii=False, indent=2))
        return

    if args.command == "update":
        updated = manager.update_report(
            args.report_id,
            report_date=args.report_date,
            generated_at=args.generated_at,
            related_paper_ids=args.paper_id,
            local_md_path=args.local_md_path,
        )
        print(json.dumps(manager.to_dict(updated), ensure_ascii=False, indent=2))
        return

    deleted = manager.delete_report(args.report_id)
    print(json.dumps({"report_id": args.report_id, "deleted": deleted}, ensure_ascii=False, indent=2))


def _as_mapping(value: Any, key_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Config '{key_name}' must be a mapping")
    return value


if __name__ == "__main__":
    main()
