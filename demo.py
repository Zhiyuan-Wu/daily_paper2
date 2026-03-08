#!/usr/bin/env python3
"""PaperFetch 演示脚本。

演示内容：
1. arXiv 在线查询（支持扩展参数 category）
2. 下载一篇论文到本地
3. 解析已下载论文为 markdown 文本（PaperParser）
4. 查询本地元信息
5. Hugging Face 指定日期查询（使用配置中的代理）
6. 下载一篇 Hugging Face 论文到本地（默认优先本地缓存）
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Iterable

from models.paper import PaperMetadata
from service.fetch import PaperFetch
from service.parse import PaperParser


def paper_to_dict(paper: PaperMetadata) -> dict:
    """将数据模型转换为可打印字典。"""
    data = asdict(paper)
    for key in ["published_at", "fetched_at", "last_accessed_at", "downloaded_at"]:
        value = data.get(key)
        if isinstance(value, datetime):
            data[key] = value.isoformat()
    return data


def print_papers(title: str, papers: Iterable[PaperMetadata], limit: int = 3) -> None:
    """简洁打印论文列表。"""
    print(f"\n=== {title} ===")
    for idx, paper in enumerate(papers):
        if idx >= limit:
            break
        payload = paper_to_dict(paper)
        print(f"[{idx + 1}] {payload['id']} | {payload['title']}")
        print(f"    published_at={payload['published_at']} | pdf={payload['local_pdf_path']}")


def main() -> None:
    """运行端到端演示流程。"""
    fetch = PaperFetch()  # 默认读取根目录 config.yaml
    parser = PaperParser()  # 默认读取根目录 config.yaml

    # 1) 在线查询 arXiv（带扩展字段 category）。
    arxiv_results = fetch.search_online(
        source="arxiv",
        start_date="2026-03-01",
        end_date="2026-03-08",
        keywords=["llm"],
        limit=3,
        category="cs.AI",
    )
    print_papers("arXiv Online Search", arxiv_results)

    # 2) 下载第一篇论文，并打印本地路径。
    if arxiv_results:
        downloaded = fetch.download_paper(arxiv_results[0].id)
        print("\nDownloaded:")
        print(f"  id={downloaded.id}")
        print(f"  local_pdf_path={downloaded.local_pdf_path}")

        # 2.1) 解析论文 PDF 为本地 markdown 文本（依赖 Ollama OCR 可用）。
        try:
            parsed_path = parser.parse_paper(downloaded.id)
            print("  parsed_text_path={}".format(parsed_path))
        except Exception as exc:  # noqa: BLE001
            print("  parse_failed={}".format(exc))

    # 3) 本地查询：只看已下载的 arXiv 论文。
    local_results = fetch.query_local(source="arxiv", has_pdf=True, limit=5)
    print_papers("Local Metadata (arXiv + has_pdf=true)", local_results, limit=5)

    # 4) Hugging Face 指定日期查询（依赖代理可用性）。
    try:
        hf_results = fetch.search_online(
            source="huggingface",
            start_date="2026-03-06",
            end_date="2026-03-06",
            keywords=["language"],
            limit=3,
        )
        print_papers("HuggingFace Daily Papers", hf_results)

        # 5) 下载第一篇 HuggingFace 论文（若已缓存，则不会重复下载）。
        if hf_results:
            hf_downloaded = fetch.download_paper(hf_results[0].id)
            print("\nHuggingFace Downloaded:")
            print(f"  id={hf_downloaded.id}")
            print(f"  local_pdf_path={hf_downloaded.local_pdf_path}")
    except Exception as exc:  # noqa: BLE001
        print("\nHuggingFace 查询未成功（通常是代理不可用）：")
        print(f"  {exc}")


if __name__ == "__main__":
    main()
