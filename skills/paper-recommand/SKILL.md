---
name: paper-recommand
description: A SOP workflow to fetch latest acdamic paper and generate a report. 
metadata:
  {
    "openclaw": { "emoji": "🗒️", "requires": {} },
  }
---

# Daily Paper Briefing Workflow

**Objective:** Execute a complete research briefing cycle via daily_paper2 CLI: fetch recent metadata, generate a market overview, select the most relevant paper based on user interests, perform deep text analysis, and compile a final Chinese report.

**Prerequisites:**
- **Local CLI Working Directory:** `~/.openclaw/workspace/daily_paper2`
- **Environment:** `source .venv/bin/activate`
- **User Interest:** Infer user interests from conversation history (e.g., *Deep Learning, Large Language Models, Agents*) or use default keywords if history is unavailable.

## Workflow

#### Step 1: Fetch Recent Metadata (Last 7 Days)
Retrieve paper metadata from the last 7 days. The output is saved as a JSON file containing titles, authors, and abstracts for subsequent analysis.

```bash
cd ~/.openclaw/workspace/daily_paper2 && \
source .venv/bin/activate && \
python scripts/paper_fetch_cli.py search-online \
  --source arxiv \
  --start-date $(date -d "7 days ago" +%Y-%m-%d) \
  --end-date $(date +%Y-%m-%d) \
  --keywords "Deep Learning,Large Language Models,Agent" \
  --limit 50 \
  > raw_metadata_260310.json
```

*(Note: Replace 260310 with current date to avoide overwrite history files)*

#### Step 2: Generate Market Overview & Select Target
**Action:** Analyzes `raw_metadata_260310.json` to summarize the landscape and identify the single most valuable paper for a deep dive based on your specific interests.

*   **Output File:** `daily_paper_overview_260310.md`
*   **Content Requirements:**
    1.  **Theme Coverage:** What are the dominant topics in the last 7 days?
    2.  **Key Works:** List 3-5 notable papers with brief descriptions.
    3.  **Selection Decision:** Explicitly state the `paper_id` chosen for the "Deep Dive" and justify the choice.

#### Step 3: Download & Parse the Selected Paper
Execute the download and full-text extraction for the **single** `paper_id` selected in Step 2.

**Download PDF**
```bash
cd ~/.openclaw/workspace/daily_paper2 && \
source .venv/bin/activate && \
python scripts/paper_fetch_cli.py download <PAPER_ID>
```
*(Replace `<PAPER_ID>` with the ID identified in Step 2, e.g., `arxiv:2403.12345`)*

**Extract Full Text (OCR)**
Convert the downloaded PDF into a structured Markdown file for analysis. This may take a few minutes.
```bash
cd ~/.openclaw/workspace/daily_paper2 && \
source .venv/bin/activate && \
python scripts/paper_parse_cli.py paper <PAPER_ID>
```
*Result:* A parsed markdown file is saved to `data/parsed/<PAPER_ID>.md`.

#### Step 4: Deep Dive Analysis
**Action:** Reads the full text from the parsed markdown file generated in Step 3.

*   **Output File:** `daily_paper_deepdive_260310.md`
*   **Content Requirements:**
    1.  **Background & Problem:** What specific gap or challenge does this paper address?
    2.  **Limitations of Prior Work:** What are the mainstream/baseline methods, and why do they fail in this context?
    3.  **Motivation & Core Techniques:** What is the key insight? Describe the main architectural changes or algorithmic innovations.
    4.  **Results & Conclusion:** What are the quantitative improvements? What is the final takeaway?

#### Step 5: Compile & Deliver Final Report
**Action:** Merge the insights from the Overview (Step 2) and the Deep Dive (Step 4) into a single, cohesive report.

*   **Output File:** `daily_paper_final_260310.md`
*   **Language:** **Chinese (Simplified)**
*   **Structure:**
    1.  **TL;DR:** A concise 3-sentence summary of the entire briefing.
    2.  **今日论文概况 (Today's Overview):** Synthesized from `daily_paper_overview_260310.md`, covering trends and key mentions.
    3.  **重点论文推荐 (Featured Paper Recommendation):** The detailed analysis from `daily_paper_deepdive_260310.md`, focusing on the selected paper.
