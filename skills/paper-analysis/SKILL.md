---
name: paper-analysis
description: Describe the best practice and useful tools for deep analysis of a specific arxiv paper.
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

REPORT_MD="data/analysis/paper_analysis_${SAFE_PAPER_ID}_${TODAY}.md"
QUESTIONS_MD="$TMP_DIR/questions.md"
ANALYSIS_MD="$TMP_DIR/analysis.md"
mkdir -p data/analysis
```

## Step 1: Check PDF Download Status and Complete if Missing

Check current paths:

```bash
sqlite3 data/papers.db "SELECT id, local_pdf_path FROM papers WHERE id = '$PAPER_ID';"
```

If no row returned, or `local_pdf_path` is empty or file missing, run:

```bash
python scripts/paper_fetch_cli.py download "$PAPER_ID" --source "$SOURCE"
```

Verify again:

```bash
sqlite3 data/papers.db "SELECT id, local_pdf_path FROM papers WHERE id = '$PAPER_ID';"
```

## Step 2: Check Parse Status and Complete if Missing

Check parse record:

```bash
sqlite3 data/papers.db "SELECT paper_id, status, local_text_path FROM paper_parses WHERE paper_id = '$PAPER_ID';"
```

If no parse row, or `status != success`, or parsed file missing, run:

```bash
python scripts/paper_parse_cli.py paper "$PAPER_ID"
```

This may take a few minutes. Then verify full text path:

```bash
sqlite3 data/papers.db "SELECT paper_id, status, local_text_path FROM paper_parses WHERE id = '$PAPER_ID';"
```

Suggested shell scaffold:

```bash
PARSED_PATH="$(sqlite3 data/papers.db "SELECT COALESCE(local_text_path,'') FROM paper_parses WHERE id = '$PAPER_ID';")"
printf "Parsed file: %s\n" "$PARSED_PATH"
```

## Step 3: Propose Analysis Questions (Question Set)

Create question file as you are a top-tier paper reviewer, for example:

```bash
cat > "$QUESTIONS_MD" <<'EOF'
# General Review
1. What concrete problem does this paper solve, and why is the timing critical (e.g., enabling new capabilities, addressing scaling bottlenecks)?
2. What are the core theoretical or empirical assumptions, and under what data distributions or domain shifts might they fail?
3. Breakdown of method components: How do the proposed modules interact to achieve the reported performance?

# Deep Learning & LLM Specifics (Tailored for User Profile)
4. Model Architecture: Is the structural design novel (e.g., attention mechanisms, MoE, state-space models)? How does it address challenges like long-context modeling, gradient flow, or inference latency?
5. Optimization & Regularization: What optimizers, learning rate schedules, or regularization techniques (Dropout, Weight Decay, LayerNorm variants, etc.) are critical? Are there ablation studies isolating the impact of these training strategies?
6. Mathematical Rigor: Are the loss functions, objective bounds, or convergence properties mathematically well-defined? Does the paper provide theoretical justification for why the method works (beyond empirical gains)?
7. Reproducibility & Data Pipeline: Are data preprocessing steps (tokenization, filtering, augmentation) and training hyperparameters clearly defined? Is the experimental setup detailed enough to reconstruct the results?

# Critical Analysis
8. Baseline Fairness: Are baselines truly SOTA? Is the comparison performed under identical compute budgets, data splits, and evaluation protocols?
9. Limitations & Scaling: What are the computational costs (FLOPs, memory footprint) vs. performance gains? Does the method degrade on out-of-distribution (OOD) data or specific edge cases? Is there evidence of overfitting?
10. Actionable Takeaway: What is the most valuable engineering insight for building production-grade ML systems, LLM applications, or autonomous agents?
EOF
```

## Step 4: Analyze Full Text Against Questions

Action:
1. Read full text markdown from parsed path.
2. Answer each question in `$QUESTIONS_MD` with evidence from the paper.
3. Write/Append structured analysis to `$ANALYSIS_MD`.


## Step 5: Repeat Question - Answer Loop for Deeper Analysis 

Action:
1. Go to Step3 for another round deeper questions (especaily paper-related questions rather than general review questions).
2. quit loop if no further question required or looped > 5 times.


## Step 6: Generate Final Paper Interpretation Markdown

Action: 
1. Read `$PARSED_PATH`, `$QUESTIONS_MD` and `$ANALYSIS_MD`.
2. summarize all findings into final report markdown at: `$REPORT_MD`.

Required sections:
1. Background and target problem.
2. Limitations of prior work.
3. Core motivation and method breakdown.
4. Quantitative results and conclusion.
5. Valuable QA result and comments.
6. Next step suggestion or any new ideas.

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
1. Interpretation markdown: `data/analysis/paper_analysis_<paper_id>_<YYYY-MM-DD>.md`
2. `activity.ai_report_summary` updated
3. `activity.ai_report_path` updated
