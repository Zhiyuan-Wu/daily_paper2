# PaperExtendMetadata 模块说明

## 1. 功能概览
`service/extend_metadata/` 提供论文扩展元信息抽取能力，主入口类为 `PaperExtendMetadataService`。

对外能力：
1. 单篇扩展元信息获取：输入 `paper_id`，自动下载 PDF、只解析首页、调用 OpenAI Chat 接口抽取扩展字段，并写入数据库。
2. 增量更新：仅处理 `papers` 表中尚未写入扩展元信息的论文。
3. 多使用方式：支持 Python import 与 CLI。
4. 可复用现有模块：内部复用 `PaperFetch` 和 `PaperParser`，避免重复实现下载与 OCR。

## 2. 设计原则
1. 复用既有能力：下载交给 `fetch`，OCR 交给 `parse`，本模块只负责“首页抽取”和结构化持久化。
2. 首页优先：只解析论文第一页，控制成本并贴近作者单位、关键词、GitHub 链接等信息的高频出现位置。
3. 增量优先：以 `extend_metadata` 表是否已有 `paper_id` 为准，只补齐缺失数据。
4. 配置驱动：OpenAI `base_url / api_key / model / timeout` 以及表名均来自 `config.yaml`。
5. 结构化输出：强制要求模型返回固定 JSON 字段，服务端再做归一化与去重。
6. 字段稳定：数据库字段名按需求使用 `affliations`，即使该拼写并非常见写法，也保持一致，避免上下游字段漂移。

## 3. 配置项（config.yaml）
```yaml
paper_extend_metadata:
  db_path: data/papers.db
  table_name: extend_metadata
  openai:
    base_url: "https://api.openai.com/v1"
    api_key: ""
    model: "gpt-4.1-mini"
    timeout_seconds: 120
```

字段说明：
1. `db_path`：sqlite 数据库路径，默认与 `papers` 共用同一个库。
2. `table_name`：扩展元信息表名，默认 `extend_metadata`。
3. `openai.base_url`：OpenAI 兼容聊天接口地址，通常带 `/v1`。
4. `openai.api_key`：API Key；为空时会优先读取项目根目录 `.env` 中的 `OPENAI_API_KEY`，再回退到进程环境变量 `OPENAI_API_KEY`，若仍为空则使用占位值 `test-key`。
5. `openai.model`：用于结构化抽取的聊天模型。
6. `openai.timeout_seconds`：调用超时。
7. 抽取提示词固定维护在代码文件 [config.py](/Users/imac/.openclaw/workspace/daily_paper2/service/extend_metadata/config.py) 中，默认不走配置文件。

## 4. 数据表

### 4.1 `extend_metadata`
1. `paper_id`：主键，关联 `papers.id`
2. `abstract_cn`：原始摘要的中文翻译
3. `affliations`：作者单位列表，JSON 字符串
4. `keywords`：关键词列表，JSON 字符串
5. `github_repo`：关联 GitHub 仓库
6. `extracted_at`：提取时间（UTC ISO 8601）

## 5. 单篇提取流程
1. 检查 `extend_metadata` 是否已存在该 `paper_id`。
2. 若不存在，调用 `PaperFetch.download_paper()`，确保本地 PDF 存在。
3. 调用 `PaperParser.parse_pdf_first_page()`，只 OCR 第一页，不写入 `paper_parses` 表。
4. 组装论文基础信息、原始摘要、首页 OCR 文本，请求 OpenAI Chat 接口。
5. 将返回 JSON 归一化后写入 `extend_metadata`。
6. 返回 JSON 结构结果。

## 6. Python API 使用
```python
from service.extend_metadata import PaperExtendMetadataService

service = PaperExtendMetadataService()

# 1) 获取一篇论文的扩展元信息
payload = service.get_extended_metadata("arxiv:2603.05500")
print(payload["abstract_cn"])
print(payload["affliations"])
print(payload["keywords"])
print(payload["github_repo"])

# 2) 读取数据库中已保存的记录
record = service.get_record("arxiv:2603.05500")
if record:
    print(record.to_dict())

# 3) 增量同步所有尚未提取的论文
result = service.sync_incremental()
print(result.processed_paper_count, result.failed_paper_count)
```

### 6.1 常用参数
```python
service = PaperExtendMetadataService(
    db_path="data/papers.db",
    table_name="extend_metadata",
    openai_base_url="https://api.openai.com/v1",
    openai_api_key="YOUR_API_KEY",
    openai_model="gpt-4.1-mini",
    openai_timeout=120,
)

payload = service.get_extended_metadata(
    "arxiv:2603.05500",
    force_refresh=True,
)
```

说明：
1. `force_refresh=False` 时，若数据库已有记录，默认直接返回缓存结果。
2. `force_refresh=True` 时，会重新解析首页并重新调用模型覆盖旧记录。
3. 若 `config.yaml` 中 `openai.api_key` 为空，可在项目根目录创建 `.env`：

```bash
OPENAI_API_KEY=your_api_key_here
```

## 7. CLI 使用
脚本位置：`scripts/paper_extend_metadata_cli.py`

1. 提取单篇论文：
```bash
python scripts/paper_extend_metadata_cli.py paper arxiv:2603.05500
```

2. 强制重算一篇论文：
```bash
python scripts/paper_extend_metadata_cli.py paper arxiv:2603.05500 --force-refresh
```

3. 增量同步：
```bash
python scripts/paper_extend_metadata_cli.py sync
```

4. 增量同步并限制处理条数：
```bash
python scripts/paper_extend_metadata_cli.py sync --limit 10
```

5. 覆盖 OpenAI / OCR 参数：
```bash
python scripts/paper_extend_metadata_cli.py \
  --db-path data/papers.db \
  --papers-dir data/papers \
  --parsed-dir data/parsed \
  --base-url https://api.openai.com/v1 \
  --api-key YOUR_API_KEY \
  --model gpt-4.1-mini \
  --ocr-endpoint http://localhost:11434/api/chat \
  --ocr-model glm-ocr \
  paper arxiv:2603.05500
```

## 8. 返回 JSON 样例
```json
{
  "paper_id": "arxiv:2603.05500",
  "abstract_cn": "本文提出了一种……",
  "affliations": [
    "OpenAI",
    "Tsinghua University"
  ],
  "keywords": [
    "large language models",
    "reasoning",
    "agents"
  ],
  "github_repo": "https://github.com/example/project",
  "extracted_at": "2026-03-18T12:34:56+00:00"
}
```

## 9. 测试
1. 单元测试：`tests/test_paper_extend_metadata_unit.py`
2. 端到端测试：`tests/test_paper_extend_metadata_e2e.py`

运行：
```bash
pytest -q tests/test_paper_extend_metadata_unit.py tests/test_paper_extend_metadata_e2e.py
```

端到端测试说明：
1. 使用真实 arXiv 查询和 PDF 下载。
2. 使用伪造 OCR / OpenAI 服务，避免依赖线上模型配额，同时仍可真实验证下载文件和数据库状态。
