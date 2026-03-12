#!/usr/bin/env python3
"""PaperFetch 演示脚本。

演示内容：
1. arXiv 在线查询（支持扩展参数 category）
2. 下载一篇论文到本地
3. 解析已下载论文为 markdown 文本（PaperParser）
4. 写入用户交互记录（PaperActivityManager）
5. 创建一条日报记录（DailyReportManager）
6. 查询某日的日报记录
7. Hugging Face 指定日期查询（使用配置中的代理）
8. 下载一篇 Hugging Face 论文到本地（默认优先本地缓存）
9. 增量构建论文向量库并执行语义检索（PaperEmbeddingService）
10. 执行推荐（PaperRecommandService：time / interaction / fusion / semantic）
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Iterable

from models.paper import PaperMetadata
from service.fetch import PaperFetch
from service.embedding import PaperEmbeddingService
from service.activity_management import PaperActivityManager
from service.parse import PaperParser
from service.recommand import PaperRecommandService
from service.report_management import DailyReportManager


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


def print_recommand_rows(title: str, rows: list, limit: int = 5) -> None:
    print(f"\n=== {title} ===")
    for idx, row in enumerate(rows[:limit], start=1):
        print(f"[{idx}] id={row.paper.id} score={row.score:.4f}")
        print(f"    title={row.paper.title}")
        print(f"    algorithm_scores={row.algorithm_scores}")


def main() -> None:
    """运行端到端演示流程。"""
    fetch = PaperFetch()  # 默认读取根目录 config.yaml
    parser = PaperParser()  # 默认读取根目录 config.yaml
    activity_manager = PaperActivityManager()  # 默认读取根目录 config.yaml
    report_manager = DailyReportManager()  # 默认读取根目录 config.yaml
    recommand_service = PaperRecommandService()  # 默认读取根目录 config.yaml

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
    downloaded: PaperMetadata | None = None
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

    # 3) 为下载论文写入用户活动，供 interaction 推荐算法使用。
    if downloaded:
        activity = activity_manager.create_activity(
            downloaded.id,
            recommendation_records=[datetime.now().isoformat()],
            user_notes="demo note: promising work",
            like=1,
            overwrite=True,
        )
        print("\nActivity Updated:")
        print(f"  id={activity.id}")
        print(f"  like={activity.like}")
        print(f"  recommendation_records={activity.recommendation_records}")
        print(f"  user_notes={activity.user_notes}")

    # 4) 生成一条日报记录，关联当前在线查询到的论文。
    report_date = datetime.now().date().isoformat()
    report_id = f"daily-{report_date}"
    related_ids = [paper.id for paper in arxiv_results[:3]]
    if downloaded and downloaded.id not in related_ids:
        related_ids.insert(0, downloaded.id)

    report_record = report_manager.create_report(
        report_id=report_id,
        report_date=report_date,
        related_paper_ids=related_ids,
        local_md_path=f"data/reports/{report_id}.md",
        overwrite=True,
    )
    print("\nDaily Report Created:")
    print(f"  id={report_record.id}")
    print(f"  report_date={report_record.report_date}")
    print(f"  generated_at={report_record.generated_at}")
    print(f"  related_paper_ids={report_record.related_paper_ids}")
    print(f"  local_md_path={report_record.local_md_path}")

    report_rows = report_manager.list_reports(limit=3, report_date=report_date)
    print(f"\nDaily Reports ({report_date}): {len(report_rows)}")
    for idx, item in enumerate(report_rows, start=1):
        print(f"  [{idx}] id={item.id} papers={len(item.related_paper_ids)} path={item.local_md_path}")

    # 5) Hugging Face 指定日期查询（依赖代理可用性）。
    try:
        hf_results = fetch.search_online(
            source="huggingface",
            start_date="2026-03-06",
            end_date="2026-03-06",
            keywords=["language"],
            limit=3,
        )
        print_papers("HuggingFace Daily Papers", hf_results)

        # 6) 下载第一篇 HuggingFace 论文（若已缓存，则不会重复下载）。
        if hf_results:
            hf_downloaded = fetch.download_paper(hf_results[0].id)
            print("\nHuggingFace Downloaded:")
            print(f"  id={hf_downloaded.id}")
            print(f"  local_pdf_path={hf_downloaded.local_pdf_path}")
    except Exception as exc:  # noqa: BLE001
        print("\nHuggingFace 查询未成功（通常是代理不可用）：")
        print(f"  {exc}")

    # 7) 论文向量化增量同步 + 语义检索（依赖 Ollama embed 可用）。
    try:
        embedding_service = PaperEmbeddingService()  # 默认读取根目录 config.yaml
        version = embedding_service.sync_incremental(limit=50)
        print("\nEmbedding Sync:")
        print(f"  version_id={version.id}")
        print(f"  processed={version.processed_paper_count}")
        print(f"  max_fetched_at={version.max_fetched_at}")
        print(f"  model={version.embedding_model}")
        print(f"  embedding_dim={version.embedding_dim}")

        hits = embedding_service.search(
            "large language model reasoning",
            top_k=3,
            fetched_from="2026-03-01",
            fetched_to="2026-03-31",
        )
        print(f"\nSemantic Search Hits: {len(hits)}")
        for idx, hit in enumerate(hits, start=1):
            print(f"  [{idx}] id={hit.paper.id} distance={hit.distance:.6f}")
            print(f"      title={hit.paper.title}")
    except Exception as exc:  # noqa: BLE001
        print("\nEmbedding 检索未成功（通常是 Ollama embed 服务不可用）：")
        print(f"  {exc}")

    # 8) 推荐模块演示。
    time_rows = recommand_service.recommend(algorithm="time", top_k=5)
    print_recommand_rows("Recommand Time", time_rows)

    interaction_rows = recommand_service.recommend(algorithm="interaction", top_k=5)
    print_recommand_rows("Recommand Interaction", interaction_rows)

    fusion_rows = recommand_service.recommend(top_k=5)  # default: fusion
    print_recommand_rows("Recommand Fusion", fusion_rows)

    try:
        semantic_rows = recommand_service.recommend(
            algorithm="semantic",
            query="large language model reasoning",
            top_k=5,
        )
        print_recommand_rows("Recommand Semantic", semantic_rows)
    except Exception as exc:  # noqa: BLE001
        print("\nRecommand semantic 未成功（通常是 embedding 检索不可用）：")
        print(f"  {exc}")


if __name__ == "__main__":
    main()
