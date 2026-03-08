# PaperParser 模块说明

## 1. 功能概览
`service/parse/` 提供独立的论文解析能力，主入口类为 `PaperParser`。

对外能力：
1. 图片解析：输入本地图片路径或 base64（单个/列表），调用 Ollama OCR 返回文本。
2. PDF 解析：输入本地 PDF 路径（单个/列表），先用 `pdf2image` 转页面图片，再复用图片解析。
3. 论文解析：输入 `paper_id`，从 sqlite 读取论文和本地 PDF 路径，解析后写入 `data/parsed/{id}.md`，并记录数据库状态。

## 2. 设计原则
1. 独立模块：`service/parse` 不依赖 `service/fetch` 的运行逻辑。
2. 数据兼容：复用同一个 sqlite（默认 `data/papers.db`），读取 `papers` 表中的 `id/local_pdf_path`。
3. 配置兼容：从根目录 `config.yaml` 的 `paper_parse` 读取默认值；若缺失可回退兼容。
4. 可追踪：新增 `paper_parses` 表记录解析状态、错误信息、页面数、输出路径和模型信息。

## 3. 配置项（config.yaml）
```yaml
paper_parse:
  db_path: data/papers.db
  parsed_dir: data/parsed
  pdf:
    dpi: 200
  ollama:
    endpoint: "http://localhost:11434/api/chat"
    model: "glm-ocr"
    prompt: "Text Recognition:"
    timeout_seconds: 120
```

说明：
1. `db_path`：解析状态和论文元数据使用的 sqlite 路径。
2. `parsed_dir`：最终 markdown 文本落盘目录。
3. `pdf.dpi`：PDF 转图片的分辨率。
4. `ollama.*`：OCR 模型配置。

## 4. 数据模型与数据库
1. 数据模型：`models/paper_parse.py` 中 `PaperParseRecord`
2. 新增数据表：`paper_parses`

核心字段：
1. `paper_id`：对应 `papers.id`
2. `status`：`success` / `failed`
3. `local_text_path`：本地 markdown 路径
4. `parsed_at`、`updated_at`
5. `error_message`
6. `page_count`
7. `ocr_model`

兼容列扩展：
1. 若 `papers` 表中不存在 `local_text_path`，解析模块会自动补列并写入该路径。

## 5. Python API 用法
```python
from service.parse import PaperParser

parser = PaperParser()

# 1) 图片 OCR（单个）
text = parser.parse_images("data/demo.jpg")

# 2) 图片 OCR（多个）
texts = parser.parse_images(["data/demo1.jpg", "data/demo2.jpg"])

# 3) PDF OCR
pdf_text = parser.parse_pdfs("data/papers/arxiv_2603.05500.pdf")

# 4) 按 paper_id 解析并落盘
local_md_path = parser.parse_paper("arxiv:2603.05500")
print(local_md_path)
```

## 6. CLI 用法
脚本位置：`scripts/paper_parse_cli.py`

1. 图片解析：
```bash
python scripts/paper_parse_cli.py image \
  --image data/demo.jpg
```

2. PDF 解析：
```bash
python scripts/paper_parse_cli.py pdf \
  --pdf data/papers/arxiv_2603.05500.pdf
```

3. 按论文 id 解析：
```bash
python scripts/paper_parse_cli.py paper arxiv:2603.05500
```

常用全局参数：
1. `--config`：配置文件路径
2. `--db-path`
3. `--parsed-dir`
4. `--endpoint --model --prompt --timeout`
5. `--dpi`

## 7. 测试
1. 单元测试：`tests/test_paper_parse_unit.py`
2. 端到端测试：`tests/test_paper_parse_e2e.py`

运行：
```bash
pytest -q tests/test_paper_parse_unit.py tests/test_paper_parse_e2e.py
```
