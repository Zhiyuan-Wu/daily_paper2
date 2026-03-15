# PaperEmbedding 模块说明

## 1. 功能概览
`service/embedding/` 提供论文语义向量化与检索能力，主入口类为 `PaperEmbeddingService`。

对外能力：
1. 增量向量化：只为尚未写入 embedding 的论文抽取元信息文本，调用 Ollama `/api/embed` 计算向量并持久化。
2. 语义检索：输入查询文本，返回 top-k 论文元信息 + 距离（支持时间过滤）。
3. embedding 服务：支持单条/批量输入文本，直接返回 embedding 向量。
4. 多使用方式：支持 Python import 与 CLI。

## 2. 设计原则
1. 单库持久化：默认复用 `data/papers.db`，同时保存 `papers` 元数据和向量表。
2. 增量优先：以“是否已有 embedding”为准，只补齐缺失索引，避免重复计算已完成论文。
3. 可观测：每次同步都会返回同步摘要（同步时间、最大 fetched_at、处理条数、模型、向量维度）。
4. 配置驱动：Ollama 地址、模型名、超时、top-k、batch_size 都由 `config.yaml` 控制。
5. 兼容可用性：当 Ollama 或 sqlite-vec 不可用时，服务会抛出明确异常，e2e 测试按条件跳过。

## 3. 配置项（config.yaml）
```yaml
paper_embedding:
  db_path: data/papers.db
  embedding_table: paper_embeddings
  default_top_k: 5
  default_batch_size: 8
  ollama:
    endpoint: "http://localhost:11434/api/embed"
    model: "qwen3-embedding:0.6b"
    timeout_seconds: 120
```

字段说明：
1. `db_path`：sqlite 数据库路径。
2. `embedding_table`：保存 `paper_id/meta_text/vector` 的向量表。
3. `default_top_k`：检索默认返回条数。
4. `default_batch_size`：批量向量化默认 batch。
5. `ollama.endpoint/model/timeout_seconds`：Ollama embedding 服务配置。

## 3.1 环境依赖（macOS 重点）
1. 需要安装 `sqlite-vec` 与 `pysqlite3`。
2. 在 macOS 上，系统自带 `sqlite3` 通常不支持扩展加载；模块内部会优先使用 `pysqlite3` 连接 sqlite。
3. 可用以下脚本验证环境：
```bash
.venv/bin/python scripts/smoke_test_pysqlite3_sqlite_vec.py
```

## 4. 数据表

### 4.1 `paper_embeddings`
1. `paper_id`：主键，关联 `papers.id`
2. `meta_text`：元信息拼接后的语义文本
3. `embedding`：sqlite-vec 序列化向量（二进制）
4. `fetched_at`：对应 `papers.fetched_at`
5. `embedded_at`：向量计算时间
6. `embedding_model` / `embedding_dim`：模型和维度元信息

## 5. Python API 使用
```python
from service.embedding import PaperEmbeddingService

service = PaperEmbeddingService()

# 1) embedding 单条
vec = service.embed_text("Why is the sky blue?")

# 2) embedding 批量
vectors = service.embed_texts([
    "large language model reasoning",
    "diffusion model image generation",
])

# 3) 增量同步向量库
result = service.sync_incremental()
print(result.processed_paper_count)

# 4) 语义检索 + 时间过滤
hits = service.search(
    "llm reasoning",
    top_k=5,
    fetched_from="2026-03-01",
    fetched_to="2026-03-31",
)
for hit in hits:
    print(hit.paper.id, hit.distance, hit.paper.title)
```

## 6. CLI 使用
脚本位置：`scripts/paper_embedding_cli.py`

1. 增量同步：
```bash
python scripts/paper_embedding_cli.py sync
```

2. 强制全量重建：
```bash
python scripts/paper_embedding_cli.py sync --force-full
```

3. 检索：
```bash
python scripts/paper_embedding_cli.py search "llm reasoning" --top-k 5 \
  --fetched-from 2026-03-01 --fetched-to 2026-03-31
```

4. embedding（批量）：
```bash
python scripts/paper_embedding_cli.py embed --text "hello" --text "world"
```

## 7. 元信息拼接规则
默认拼接字段：
1. `title`
2. `authors`
3. `abstract`
4. `keywords/tags/category/categories/subjects`（从 `papers.extra` 中提取）
5. `source` 和 `published_at`

最终生成的文本格式示例：
```text
title: ...
authors: ...
abstract: ...
keywords: ...
source: arxiv
published_at: 2026-03-08T12:00:00+00:00
```

## 8. 测试
1. 单元测试：`tests/test_paper_embedding_unit.py`
2. 端到端测试：`tests/test_paper_embedding_e2e.py`

运行：
```bash
pytest -q tests/test_paper_embedding_unit.py tests/test_paper_embedding_e2e.py
```
