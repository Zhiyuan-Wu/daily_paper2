# PaperFetch 模块说明

## 1. 功能概览
`service/fetch/` 提供统一论文抓取能力，主入口类为 `PaperFetch`。

对外能力：
1. 在线查询：支持多论文源 + 日期范围 + 关键词 + 插件扩展参数。
2. 论文下载：按 id 下载 PDF 到本地，自动更新 sqlite 中 `local_pdf_path`。

## 2. 配置驱动（config.yaml）
项目根目录 `config.yaml` 是默认值来源，重要参数不在业务代码中硬编码。

```yaml
paper_fetch:
  db_path: data/papers.db
  papers_dir: data/papers
  max_downloaded_papers: 100
  sources:
    arxiv:
      timeout_seconds: 30
      default_query: "all:machine learning"
      default_search_limit: 20
      max_results_multiplier: 3
      download_chunk_size: 65536
    huggingface:
      timeout_seconds: 30
      use_proxy: true
      proxy_url: "http://localhost:7890"
      default_search_limit: 20
      download_chunk_size: 65536
  cli:
    default_online_limit: 20
```

说明：
- `db_path`、`papers_dir`、`max_downloaded_papers` 控制本地存储与 LRU 容量。
- `sources.arxiv`、`sources.huggingface` 控制各插件请求超时、默认行为等。
- `sources.huggingface.proxy_url` 默认代理地址为 `http://localhost:7890`。
- `cli` 控制命令行默认分页参数。

## 3. 目录结构
- `models/paper.py`: 数据模型 `PaperMetadata`
- `service/fetch/config.py`: 配置加载
- `service/fetch/paper_fetch.py`: 门面类 `PaperFetch`
- `service/fetch/repository.py`: sqlite 仓储层
- `service/fetch/sources/base.py`: 插件抽象基类
- `service/fetch/sources/arxiv_source.py`: arXiv 插件
- `service/fetch/sources/huggingface_source.py`: Hugging Face 插件
- `scripts/paper_fetch_cli.py`: CLI
- `demo.py`: 功能演示脚本

## 4. 数据模型
`PaperMetadata` 关键字段：
- `id`: 内部唯一 id，格式 `source:source_id`
- `title` / `authors` / `published_at` / `abstract`
- `online_url` / `pdf_url` / `local_pdf_path`
- `fetched_at` / `last_accessed_at` / `downloaded_at`
- `extra`: 插件扩展字段

## 5. SQLite 与 LRU
默认：
- sqlite: `data/papers.db`
- pdf目录: `data/papers/`

行为：
- 在线查询结果会自动写入 sqlite，但只插入不存在的条目，不会改写已有条目。
- 下载后更新本地路径与时间戳。
- 下载默认优先使用本地缓存；仅在 `force_refresh=True`（或 CLI `--force-refresh`）时强制重新下载。
- 若目标目录已有目标文件（同名 pdf），默认不会重复下载。
- 当本地 PDF 数量超过 `max_downloaded_papers`，按 `last_accessed_at` 最久未使用优先淘汰：
  - 删除本地文件
  - 清空对应元信息 `local_pdf_path`

## 6. Python API 示例
```python
from service.fetch import PaperFetch

fetch = PaperFetch()  # 默认读取根目录 config.yaml

papers = fetch.search_online(
    source="arxiv",
    start_date="2026-03-01",
    end_date="2026-03-08",
    keywords=["llm"],
    category="cs.AI",  # 插件扩展参数
)

saved = fetch.download_paper(papers[0].id)
print(saved.local_pdf_path)
```

## 7. CLI 用法
`--config` 可切换配置文件（默认根目录 `config.yaml`）。

1. 在线查询
```bash
python scripts/paper_fetch_cli.py search-online \
  --source arxiv \
  --start-date 2026-03-01 \
  --end-date 2026-03-08 \
  --keywords llm,reasoning \
  --extra category=cs.AI
```

2. 下载
```bash
python scripts/paper_fetch_cli.py download arxiv:2603.01234
```

强制刷新下载：
```bash
python scripts/paper_fetch_cli.py download arxiv:2603.01234 --force-refresh
```

## 8. 演示脚本
根目录 `demo.py` 展示：
1. arXiv 在线查询
2. 下载第一篇论文
3. Hugging Face 指定日期查询（支持代理）
4. 下载第一篇 Hugging Face 论文

运行：
```bash
python demo.py
```

## 9. 测试
- 单元测试：`tests/test_paper_fetch_unit.py`
- 端到端测试：`tests/test_paper_fetch_e2e.py`

运行：
```bash
pytest -q
```
