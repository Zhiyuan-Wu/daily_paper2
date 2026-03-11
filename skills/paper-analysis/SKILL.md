---
name: paper-analysis
description: Analyze one paper in depth and produce a structured markdown report.
metadata:
  {
    "openclaw": { "emoji": "🔬", "requires": {} },
  }
---

# Paper Analysis Workflow

**Objective:** perform a deep AI interpretation for one target paper and output a markdown report.

## Inputs
- `paper_id`: target paper id, for example `arxiv:2603.08706`.

## Steps
1. Locate metadata in sqlite and confirm title, abstract, source, and links.
2. If local parsed text exists, use it as the primary source.
3. If local parsed text is missing, attempt to fetch/read the paper text from available local/online sources.
4. Produce a structured Chinese report containing:
   - 研究背景与问题定义
   - 核心方法与技术路线
   - 实验设置与关键结果
   - 优势、局限与潜在风险
   - 对业务/工程落地的启发
5. Save the report to a markdown file under `data/reports/`.
6. Print progress and result file path to stdout.
