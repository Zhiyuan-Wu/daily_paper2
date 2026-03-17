---
name: paper-recommand
description: Describe the best practice and useful tools for downloading recent paper from multiple online sources and generate a daily briefing for user.
---

# Daily Paper Report Workflow

Objective: build a persona-driven daily report. First infer user profile from `activity` likes/notes, then fetch latest papers using that profile, incrementally refresh extended metadata, refresh embedding index, run recommendations, pick one featured paper, generate final report, persist report row, and write recommendation records into `activity`.

## Prerequisites

```bash
cd ~/.openclaw/workspace/daily_paper2
source .venv/bin/activate
```

CLI Tools you can use:
- **paper_fetch_cli**: search online paper or download a specific paper.
- **paper_parse_cli**: parse a pdf file into a markdown text file using OCR.
- **paper_extend_metadata_cli**: extract or incrementally sync extended metadata such as Chinese abstract, affiliations, and keywords.
- **paper_activity_cli**: CRUD for recording user notes / generated analysis etc. related to a paper.
- **paper_report_cli**: CRUD for recording generated daily reports arctifact.
- **paper_embedding_cli**: incremental vector sync and semantic search.
- **paper_recommand_cli**: recommendation service CLI.

(*Note: detailed CLI usage document are located at docs/XXX.md*) 

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

PROFILE_MD="$TMP_DIR/user_profile_${STAMP}.md"
RAW_ARXIV_JSON="$TMP_DIR/raw_arxiv_${STAMP}.json"
RAW_HF_JSON="$TMP_DIR/raw_hf_${STAMP}.json"
RECOMMAND_JSON="$TMP_DIR/recommand_${STAMP}.json"
OVERVIEW_MD="$TMP_DIR/daily_overview_${STAMP}.md"
FINAL_MD="data/reports/daily_paper_${TODAY}.md"

mkdir -p data/reports
```

## Step 1: Build User Persona from Activity

```bash
sqlite3 data/papers.db "
SELECT
  p.id,
  p.title,
  p.abstract,
  p.source,
  a.like,
  COALESCE(a.user_notes, '') AS user_notes
FROM activity a
LEFT JOIN papers p ON p.id = a.id
WHERE a.like = 1 OR LENGTH(TRIM(COALESCE(a.user_notes, ''))) > 0
ORDER BY a.like DESC, p.published_at DESC
LIMIT 80;
" > "$TMP_DIR/persona_seed.tsv"
```

Action:
1. Read `persona_seed.tsv`.
2. Summarize user persona in `$PROFILE_MD` (topics, methods, application domains, disliked patterns if available).
3. Output two explicit lines in `$PROFILE_MD`:
- `PROFILE_QUERY=<one concise natural-language query>`
- `PROFILE_KEYWORDS=<comma-separated keywords, 5~12 items>`

## Step 2: Fetch Latest Metadata with Persona Query (Last 7 Days)

Use `PROFILE_KEYWORDS` from Step 1:

```bash
python scripts/paper_fetch_cli.py search-online \
  --source arxiv \
  --start-date "$START_DATE" \
  --end-date "$TODAY" \
  --keywords "<PROFILE_KEYWORDS>" \
  --limit 60 \
  > "$RAW_ARXIV_JSON"
```

```bash
python scripts/paper_fetch_cli.py search-online \
  --source huggingface \
  --start-date "$START_DATE" \
  --end-date "$TODAY" \
  --keywords "<PROFILE_KEYWORDS>" \
  --limit 40 \
  > "$RAW_HF_JSON"
```

(*Note: Refer to docs/paper_fetch.md for detail CLI usage, e.g., arxiv `--extra category=cs.AI`*) 

## Step 3: Incrementally Refresh Extended Metadata

Action:
1. Run incremental sync for newly fetched papers before rebuilding embeddings:

```bash
python scripts/paper_extend_metadata_cli.py sync
```

2. Verify output contains `processed_paper_count`.

## Step 4: Update Embedding Vector DB After New Metadata

Action:
1. Run incremental sync for new papers:

```bash
python scripts/paper_embedding_cli.py sync
```

2. Verify output contains `processed_paper_count`.

## Step 5: Persona-Driven Recommendation and Featured Selection

Use `PROFILE_QUERY` from Step 1:

```bash
python scripts/paper_recommand_cli.py recommend \
  --algorithm fusion \
  --query "<PROFILE_QUERY>" \
  --top-k 20 \
  > "$RECOMMAND_JSON"
```

Then:
1. Read `$RECOMMAND_JSON`.
2. Select one `featured` paper (`TARGET_PAPER_ID`) and 3~8 related papers (`RELATED_PAPER_IDS`, include target).
3. Write recommendation summary to `$OVERVIEW_MD`.
4. In `$OVERVIEW_MD`, explicitly output:
- `TARGET_PAPER_ID=<paper_id>`
- `RELATED_PAPER_IDS=<id1,id2,id3,...>`

Required sections in `$OVERVIEW_MD`:
1. User persona summary.
2. Theme coverage from latest papers.
3. Recommended list (with brief rationale per item).
4. Selection rationale for featured paper.

## Step 6: Download and Parse Featured Paper

Replace `<TARGET_PAPER_ID>` with the selected paper id.

```bash
python scripts/paper_fetch_cli.py download <TARGET_PAPER_ID>
python scripts/paper_parse_cli.py paper <TARGET_PAPER_ID>
```

(*Note: Refer to docs/paper_parse.md for detail CLI usage.*) 

## Step 7: Deep Dive Analysis

Action:
1. For each `<TARGET_PAPER_ID>`, Spawn a subwokflow (subagent if possible) executing `skills/paper-analysis/SKILL.md`. This suppose to generate deep dive analysis report for each target paper at `data/analysis/paper_analysis_<paper_id>_<YYYY-MM-DD>.md`

(*Note: You can ask to safely skip download/parse status check in paper-analysis workflow, as you just did them.*) 

## Step 8: Compose Final Daily Report

Action: merge overview + deep dive into one final report markdown.

Output path must be exactly:
- `$FINAL_MD` (in `data/reports/` with today's date)

Required structure:
1. TL;DR (3 sentences)
2. Today's overview
3. Featured paper deep analysis

## Step 9: Write Recommendation Records into Activity

For each paper id in `RELATED_PAPER_IDS`, append one recommendation timestamp:

```bash
RECOMMAND_TIME="$(python - <<'PY'
from datetime import datetime, timezone
print(datetime.now(timezone.utc).isoformat())
PY
)"

# Replace with comma-separated ids from Step 5 output, e.g.:
# RELATED_PAPER_IDS_CSV="arxiv:2603.00001,arxiv:2603.00002,arxiv:2603.00003"
RELATED_PAPER_IDS_CSV="<RELATED_PAPER_IDS_CSV>"
IFS=',' read -r -a RELATED_IDS <<< "$RELATED_PAPER_IDS_CSV"

for PAPER_ID in "${RELATED_IDS[@]}"; do
  PAPER_ID="$(echo "$PAPER_ID" | xargs)"
  [ -z "$PAPER_ID" ] && continue
  python scripts/paper_activity_cli.py append-recommendation "$PAPER_ID" "$RECOMMAND_TIME"
done
```

(*Note: `append-recommendation` auto-creates missing activity rows.*)

## Step 10: Create Report Row in SQLite via Report CLI

Rules:
1. `report_id` must include today's date, example: `daily-2026-03-12`.
2. `--report-date` must use `$TODAY`.
3. `--local-md-path` must be `$FINAL_MD`.
4. Pass `--paper-id` repeatedly for related papers (must include featured paper).

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

(*Note: Refer to docs/paper_report.md for detail CLI usage.*)

## Step 11: Cleanup Temp Workspace

```bash
rm -rf "$TMP_DIR"
trap - EXIT
```
