#!/usr/bin/env python3
"""Migrate ``activity`` table by adding a strict ``like`` column."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def migrate(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='activity'"
        ).fetchone()
        if not table:
            _create_activity_table(conn)
            conn.commit()
            print(f"created activity table with like column: {db_path}")
            return

        columns = conn.execute("PRAGMA table_info(activity)").fetchall()
        names = {column[1] for column in columns}
        if "like" in names:
            print(f"skip migration: activity.like already exists ({db_path})")
            return

        conn.execute("BEGIN")
        conn.execute(
            """
            CREATE TABLE activity_new (
                id TEXT PRIMARY KEY,
                recommendation_records TEXT NOT NULL DEFAULT '[]',
                user_notes TEXT NOT NULL DEFAULT '',
                ai_report_summary TEXT NOT NULL DEFAULT '',
                ai_report_path TEXT NOT NULL DEFAULT '',
                "like" INTEGER NOT NULL DEFAULT 0 CHECK("like" IN (-1, 0, 1))
            )
            """
        )
        conn.execute(
            """
            INSERT INTO activity_new (
                id, recommendation_records, user_notes, ai_report_summary, ai_report_path, "like"
            )
            SELECT id, recommendation_records, user_notes, ai_report_summary, ai_report_path, 0
            FROM activity
            """
        )
        conn.execute("DROP TABLE activity")
        conn.execute("ALTER TABLE activity_new RENAME TO activity")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_activity_ai_report_path ON activity(ai_report_path)"
        )
        conn.commit()
        print(f"migration complete: activity.like added ({db_path})")
    finally:
        conn.close()


def _create_activity_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE activity (
            id TEXT PRIMARY KEY,
            recommendation_records TEXT NOT NULL DEFAULT '[]',
            user_notes TEXT NOT NULL DEFAULT '',
            ai_report_summary TEXT NOT NULL DEFAULT '',
            ai_report_path TEXT NOT NULL DEFAULT '',
            "like" INTEGER NOT NULL DEFAULT 0 CHECK("like" IN (-1, 0, 1))
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_activity_ai_report_path ON activity(ai_report_path)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Add like column to activity table")
    parser.add_argument("--db-path", default="data/papers.db")
    args = parser.parse_args()
    migrate(Path(args.db_path))


if __name__ == "__main__":
    main()
