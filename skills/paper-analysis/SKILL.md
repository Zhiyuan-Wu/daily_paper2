---
name: paper-analysis
description: Ensure metadata/download/parse are complete for a paper, perform full-text question-driven analysis, generate interpretation markdown, and write AI fields into activity table.
metadata:
  {
    "openclaw": { "emoji": "🔬", "requires": {} },
  }
---

# Paper Analysis Workflow

Objective: complete missing data steps for one paper (metadata, PDF, parsed text), run question-driven full-text analysis, generate final interpretation report, and persist AI analysis fields to `activity` table.

Input:
- `PAPER_ID` (example: `arxiv:2603.08706`)

## Prerequisites

```bash
cd ~/.openclaw/workspace/daily_paper2
source .venv/bin/activate
PAPER_ID="<PAPER_ID>"
SOURCE="${PAPER_ID%%:*}"
SOURCE_ID="${PAPER_ID#*:}"
TODAY="$(python - <<'PY'
from datetime import date
print(date.today().isoformat())
PY
)"

SAFE_PAPER_ID="${PAPER_ID//:/_}"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/paper-analysis-${SAFE_PAPER_ID}-XXXXXX")"
trap 'rm -rf "$TMP_DIR"' EXIT

REPORT_MD="data/reports/paper_analysis_${SAFE_PAPER_ID}_${TODAY}.md"
QUESTIONS_MD="$TMP_DIR/questions.md"
ANALYSIS_MD="$TMP_DIR/analysis.md"
mkdir -p data/reports
```

## Step 1: Check Metadata Exists

```bash
sqlite3 data/papers.db "SELECT id, source, source_id, title FROM papers WHERE id = '$PAPER_ID';"
```

If no row returned, fetch metadata by source id:

```bash
python scripts/paper_fetch_cli.py download "$SOURCE_ID" --source "$SOURCE"
```

Re-check metadata:

```bash
sqlite3 data/papers.db "SELECT id, source, source_id, title FROM papers WHERE id = '$PAPER_ID';"
```

## Step 2: Check PDF Download Status and Complete if Missing

Check current paths:

```bash
sqlite3 data/papers.db "SELECT id, local_pdf_path, local_text_path FROM papers WHERE id = '$PAPER_ID';"
```

If `local_pdf_path` is empty or file missing, run:

```bash
python scripts/paper_fetch_cli.py download "$PAPER_ID"
```

Verify again:

```bash
sqlite3 data/papers.db "SELECT id, local_pdf_path FROM papers WHERE id = '$PAPER_ID';"
```

## Step 3: Check Parse Status and Complete if Missing

Check parse record:

```bash
sqlite3 data/papers.db "SELECT paper_id, status, local_text_path FROM paper_parses WHERE paper_id = '$PAPER_ID';"
```

If no parse row, or `status != success`, or parsed file missing, run:

```bash
python scripts/paper_parse_cli.py paper "$PAPER_ID"
```

Verify full text path:

```bash
sqlite3 data/papers.db "SELECT local_text_path FROM papers WHERE id = '$PAPER_ID';"
```

At this point, full text must be available at `data/parsed/${SAFE_PAPER_ID}.md` (or db-reported path).

## Step 4: Propose Analysis Questions (Question Set)

Create question file:

```bash
cat > "$QUESTIONS_MD" <<'EOF'
1. This paper solves which concrete problem and why now?
2. What assumptions are made, and where might they fail?
3. What are the main method components and how do they interact?
4. Which baselines are used, and is comparison fair?
5. What evidence supports claimed gains (ablation, robustness, scaling)?
6. What are major limitations, risks, and reproducibility constraints?
7. What is the most actionable engineering takeaway?
EOF
```

## Step 5: Analyze Full Text Against Questions

Action:
1. Read full text markdown from parsed path.
2. Answer each question in `$QUESTIONS_MD` with evidence from the paper.
3. Write structured analysis to `$ANALYSIS_MD`.

Suggested shell scaffold:

```bash
PARSED_PATH="$(sqlite3 data/papers.db "SELECT COALESCE(local_text_path,'') FROM papers WHERE id = '$PAPER_ID';")"
printf "Parsed file: %s\n" "$PARSED_PATH"
```

## Step 6: Generate Final Paper Interpretation Markdown

Action: summarize all findings into final report markdown at:
- `$REPORT_MD`

Required sections:
1. Paper metadata snapshot
2. Problem and motivation
3. Method breakdown
4. Experimental evidence and critical assessment
5. Risks and limitations
6. Practical recommendations
7. Final verdict

## Step 7: Persist AI Fields to Activity Table

Prepare a one-line summary string (<= 300 chars), then write to activity.

Example:

```bash
SUMMARY="<one-line Chinese summary of key contribution and conclusion>"
EXISTING="$(python scripts/paper_activity_cli.py get "$PAPER_ID")"

if [ "$EXISTING" = "null" ]; then
  python scripts/paper_activity_cli.py create "$PAPER_ID" \
    --ai-report-summary "$SUMMARY" \
    --ai-report-path "$REPORT_MD"
else
  python scripts/paper_activity_cli.py update "$PAPER_ID" \
    --ai-report-summary "$SUMMARY" \
    --ai-report-path "$REPORT_MD"
fi
```

Verify write-back:

```bash
python scripts/paper_activity_cli.py get "$PAPER_ID"
```

## Step 8: Cleanup Temp Workspace

```bash
rm -rf "$TMP_DIR"
trap - EXIT
```

Deliverables:
1. Interpretation markdown: `data/reports/paper_analysis_<paper_id>_<YYYY-MM-DD>.md`
2. `activity.ai_report_summary` updated
3. `activity.ai_report_path` updated
