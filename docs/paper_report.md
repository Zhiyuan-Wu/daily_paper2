# PaperReport 模块说明

## 1. 功能概览
`service/report_management/` 提供独立的日报数据管理能力，主入口类为 `DailyReportManager`。

核心能力：
1. 使用 sqlite `report` 表记录每个日报。
2. 对外提供完整 CRUD（创建、读取、更新、删除）。
3. 同时支持 Python import 与 CLI 调用。
4. 与 `service` 下其它业务服务解耦，仅保持数据结构和配置风格兼容。

## 2. 表结构
默认表名：`report`

字段定义：
1. `id` (`TEXT PRIMARY KEY`)  
   日报记录唯一标识（例如 `daily-2026-03-11`）。
2. `report_date` (`TEXT NOT NULL`)  
   日报时间（ISO 日期，如 `2026-03-11`）。
3. `generated_at` (`TEXT NOT NULL`)  
   生成时间（ISO 时间，如 `2026-03-11T08:00:00+00:00`）。
4. `related_paper_ids` (`TEXT NOT NULL`)  
   JSON 字符串，解析后为论文 ID 列表。
5. `local_md_path` (`TEXT NOT NULL`)  
   日报 markdown 文件本地路径。

## 3. 配置项（config.yaml）
新增配置段：

```yaml
paper_report:
  db_path: data/papers.db
  table_name: report
  reports_dir: data/reports
  cli:
    default_limit: 100
```

参数说明：
1. `db_path`：sqlite 路径，默认与现有模块共享数据库。
2. `table_name`：日报表名，默认 `report`。
3. `reports_dir`：日报 markdown 默认目录（演示与调用时可复用）。
4. `cli.default_limit`：CLI `list` 子命令默认返回条数。

兼容回退：
1. 若 `paper_report` 缺失，会回退到 `paper_fetch.db_path` 或 `data/papers.db`。

## 4. Python API
入口：
```python
from service.report_management import DailyReportManager
```

### 4.1 初始化
```python
manager = DailyReportManager(
    db_path="data/papers.db",      # 可选
    table_name="report",           # 可选
    config_path="config.yaml",     # 可选
)
```

### 4.2 创建
```python
record = manager.create_report(
    report_id="daily-2026-03-11",
    report_date="2026-03-11",
    generated_at="2026-03-11T08:00:00+00:00",
    related_paper_ids=["arxiv:2603.05500", "huggingface:paper-1"],
    local_md_path="data/reports/daily-2026-03-11.md",
    overwrite=True,
)
```

### 4.3 查询与列表
```python
one = manager.get_report("daily-2026-03-11")
rows = manager.list_reports(limit=20, offset=0, report_date="2026-03-11")
```

### 4.4 更新
```python
updated = manager.update_report(
    "daily-2026-03-11",
    generated_at="2026-03-11T09:00:00+00:00",
    related_paper_ids=["arxiv:2603.05500"],
    local_md_path="data/reports/daily-2026-03-11-v2.md",
)
```

### 4.5 删除
```python
ok = manager.delete_report("daily-2026-03-11")
```

## 5. CLI 用法
脚本路径：`scripts/paper_report_cli.py`

### 5.1 创建
```bash
python scripts/paper_report_cli.py create daily-2026-03-11 \
  --report-date 2026-03-11 \
  --generated-at 2026-03-11T08:00:00Z \
  --paper-id arxiv:2603.05500 \
  --paper-id huggingface:paper-1 \
  --local-md-path data/reports/daily-2026-03-11.md
```

### 5.2 查询
```bash
python scripts/paper_report_cli.py get daily-2026-03-11
```

### 5.3 列表
```bash
python scripts/paper_report_cli.py list --limit 20 --offset 0 --report-date 2026-03-11
```

### 5.4 更新
```bash
python scripts/paper_report_cli.py update daily-2026-03-11 \
  --generated-at 2026-03-11T09:00:00+00:00 \
  --paper-id arxiv:2603.05500 \
  --local-md-path data/reports/daily-2026-03-11-v2.md
```

### 5.5 删除
```bash
python scripts/paper_report_cli.py delete daily-2026-03-11
```

## 6. 设计原则
1. 独立性：模块内部只包含自身配置、模型、仓储与管理类，不调用现有业务服务。
2. 兼容性：默认复用相同 sqlite 路径与配置文件读取方式。
3. 可测试性：模型序列化与 SQL 操作可被单测直接验证，CLI 用 e2e 测试验证真实数据库状态。
4. 可扩展性：CLI 与 Python API 对齐，便于后续接入调度器或外部系统。
