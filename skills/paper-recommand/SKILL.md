---
name: paper-recommand
description: Generate today's daily paper report with fetch+parse workflow, persist report metadata to sqlite report table, and clean temporary workspace.
metadata:
  {
    "openclaw": { "emoji": "🗒️", "requires": {} },
  }
---

# Daily Paper Report Workflow

Objective: build a complete daily report, store final markdown in `data/reports/` with today's date, create a `report` table row via CLI, and remove temp files.

## Prerequisites

```bash
cd ~/.openclaw/workspace/daily_paper2
source .venv/bin/activate
```

## Step 0: Initialize Runtime Variables and Temp Workspace

```bash
TODAY="$(python - <<'PY'
from datetime import date
print(date.today().isoformat())
PY
)"
STAMP="$(python - <<'PY'
from datetime import date
print(date.today().strftime('%Y%m%d'))
PY
)"
START_DATE="$(python - <<'PY'
from datetime import date, timedelta
print((date.today() - timedelta(days=7)).isoformat())
PY
)"

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/paper-recommand-${STAMP}-XXXXXX")"
trap 'rm -rf "$TMP_DIR"' EXIT

RAW_JSON="$TMP_DIR/raw_metadata_${STAMP}.json"
OVERVIEW_MD="$TMP_DIR/daily_paper_overview_${STAMP}.md"
DEEPDIVE_MD="$TMP_DIR/daily_paper_deepdive_${STAMP}.md"
FINAL_MD="data/reports/daily_paper_${TODAY}.md"

mkdir -p data/reports
```

## Step 1: Fetch Metadata (Last 7 Days)

```bash
python scripts/paper_fetch_cli.py search-online \
  --source arxiv \
  --start-date "$START_DATE" \
  --end-date "$TODAY" \
  --keywords "Deep Learning,Large Language Models,Agent" \
  --limit 50 \
  > "$RAW_JSON"
```

## Step 2: Build Overview and Choose Target Paper

Action:
1. Read `$RAW_JSON`.
2. Write overview markdown to `$OVERVIEW_MD`.
3. In `$OVERVIEW_MD`, explicitly output:
- `TARGET_PAPER_ID=<paper_id>`
- `RELATED_PAPER_IDS=<id1,id2,id3,...>`

Required sections in `$OVERVIEW_MD`:
1. Theme coverage in the past 7 days.
2. 3-5 notable papers.
3. Selection rationale for target paper.

## Step 3: Download and Parse Target Paper

Replace `<TARGET_PAPER_ID>` with the selected paper id.

```bash
python scripts/paper_fetch_cli.py download <TARGET_PAPER_ID>
python scripts/paper_parse_cli.py paper <TARGET_PAPER_ID>
```

## Step 4: Deep Dive Analysis

Action:
1. Read parsed full text from `data/parsed/<TARGET_PAPER_ID>.md`.
2. Write deep dive markdown to `$DEEPDIVE_MD`.

Required sections in `$DEEPDIVE_MD`:
1. Background and target problem.
2. Limitations of prior work.
3. Core motivation and method.
4. Quantitative results and conclusion.

## Step 5: Compose Final Daily Report

Action: merge overview + deep dive into one final report markdown.

Output path must be exactly:
- `$FINAL_MD` (in `data/reports/` with today's date)

Required structure:
1. TL;DR (3 sentences)
2. Today's overview
3. Featured paper deep analysis

## Step 6: Create Report Row in SQLite via Report CLI

Rules:
1. `report_id` must include today's date, example: `daily-2026-03-12`.
2. `--report-date` must use `$TODAY`.
3. `--local-md-path` must be `$FINAL_MD`.
4. Pass `--paper-id` repeatedly for related papers (at least include target paper).

Example command:

```bash
python scripts/paper_report_cli.py create "daily-${TODAY}" \
  --report-date "$TODAY" \
  --generated-at "$(python - <<'PY'
from datetime import datetime, timezone
print(datetime.now(timezone.utc).isoformat())
PY
)" \
  --paper-id <TARGET_PAPER_ID> \
  --paper-id <RELATED_PAPER_ID_2> \
  --paper-id <RELATED_PAPER_ID_3> \
  --local-md-path "$FINAL_MD" \
  --overwrite
```

## Step 7: Cleanup Temp Workspace

```bash
rm -rf "$TMP_DIR"
trap - EXIT
```

Deliverable:
1. Final report file at `data/reports/daily_paper_<YYYY-MM-DD>.md`.
2. One report row persisted in sqlite `report` table.
