# PaperActivity 模块说明

## 1. 功能概览
`service/activity_management/` 提供独立的论文活动管理能力，主入口类是 `PaperActivityManager`。

核心目标：
1. 以 sqlite `activity` 表记录论文活动信息。
2. 每条记录通过 `id` 与其它论文表（如 `papers.id`）做逻辑关联。
3. 提供完整 CRUD（创建、读取、更新、删除）能力。
4. 同时支持 Python import 和 CLI 两种使用方式。

该模块不依赖 `service/fetch` 或 `service/parse` 业务实现，仅复用统一的 sqlite 路径与配置风格。

## 2. 表结构
默认表名：`activity`

字段定义：
1. `id` (`TEXT PRIMARY KEY`)  
   论文唯一标识，用于与其它表关联（例如 `arxiv:2603.05500`）。
2. `recommendation_records` (`TEXT`)  
   JSON 字符串，内容是时间字符串列表，用于记录论文每次进入推荐列表的时间。
3. `user_notes` (`TEXT`)  
   用户阅读笔记。
4. `ai_report_summary` (`TEXT`)  
   AI 精读摘要。
5. `ai_report_path` (`TEXT`)  
   AI 精读完整报告路径。

## 3. 配置项（config.yaml）
新增配置段：

```yaml
paper_activity:
  db_path: data/papers.db
  table_name: activity
  cli:
    default_limit: 100
```

说明：
1. `db_path`：sqlite 路径，默认与其它模块兼容可共享同一数据库。
2. `table_name`：活动表名，默认 `activity`。
3. `cli.default_limit`：CLI `list` 子命令默认查询上限。

兼容回退：
1. 若未配置 `paper_activity`，模块会回退到 `paper_fetch.db_path` 或 `data/papers.db`。

## 4. Python API
入口：
```python
from service.activity_management import PaperActivityManager
```

### 4.1 初始化
```python
manager = PaperActivityManager(
    db_path="data/papers.db",      # 可选
    table_name="activity",         # 可选
    config_path="config.yaml",     # 可选
)
```

### 4.2 创建记录
```python
record = manager.create_activity(
    "arxiv:2603.05500",
    recommendation_records=["2026-03-08T10:00:00Z"],
    user_notes="先读实验部分",
    ai_report_summary="提出了新的训练框架",
    ai_report_path="data/reports/2603.05500.md",
)
```

参数：
1. `paper_id`: 论文 id（必填）
2. `recommendation_records`: 推荐时间列表（可选）
3. `user_notes`: 用户笔记（可选）
4. `ai_report_summary`: AI 摘要（可选）
5. `ai_report_path`: AI 报告路径（可选）
6. `overwrite`: 是否覆盖同 id 记录（默认 `False`）

### 4.3 查询/列表
```python
one = manager.get_activity("arxiv:2603.05500")
rows = manager.list_activities(limit=50, offset=0)
```

### 4.4 更新
```python
updated = manager.update_activity(
    "arxiv:2603.05500",
    user_notes="补充阅读笔记",
    ai_report_summary="新摘要",
)
```

说明：仅更新传入字段，未传入字段保持不变。

### 4.5 追加推荐时间
```python
updated = manager.append_recommendation("arxiv:2603.05500", "2026-03-08T11:30:00Z")
```

说明：若记录不存在，会先创建空记录再追加时间。

### 4.6 删除
```python
ok = manager.delete_activity("arxiv:2603.05500")
```

## 5. CLI 用法
脚本路径：`scripts/paper_activity_cli.py`

### 5.1 创建
```bash
python scripts/paper_activity_cli.py create arxiv:2603.05500 \
  --recommendation-time 2026-03-08T10:00:00Z \
  --user-notes "note-1" \
  --ai-report-summary "summary-1" \
  --ai-report-path "data/reports/r1.md"
```

### 5.2 查询
```bash
python scripts/paper_activity_cli.py get arxiv:2603.05500
```

### 5.3 列表
```bash
python scripts/paper_activity_cli.py list --limit 20 --offset 0
```

### 5.4 更新
```bash
python scripts/paper_activity_cli.py update arxiv:2603.05500 \
  --user-notes "note-2" \
  --ai-report-summary "summary-2"
```

### 5.5 追加推荐时间
```bash
python scripts/paper_activity_cli.py append-recommendation \
  arxiv:2603.05500 2026-03-08T11:00:00Z
```

### 5.6 删除
```bash
python scripts/paper_activity_cli.py delete arxiv:2603.05500
```

## 6. 设计原则
1. 独立性：不调用现有抓取/解析服务，避免业务耦合。
2. 兼容性：沿用相同配置结构与 sqlite 路径约定，可直接接入现有数据库。
3. 可测试性：仓储层与业务层分离，单元测试可直接验证 JSON 序列化与 SQL 状态。
4. 可运维性：CLI 与 Python API 功能对齐，便于脚本化或集成调用。
