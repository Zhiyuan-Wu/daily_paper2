# PaperRecommand 模块说明

## 1. 功能概览
`service/recommand/` 提供插件化论文推荐能力，主入口类为 `PaperRecommandService`。

支持能力：
1. 插件扩展：每种算法实现统一 `recommend(request)`，返回 `paper_id -> score(0~1)`。
2. 语义推荐插件（`semantic`）：接收查询语句，调用 embedding 检索服务返回推荐分数。
3. 交互推荐插件（`interaction`）：读取 `activity` 表，综合 `like`、`user_notes`、`recommendation_records` 计算分数。
4. 时间推荐插件（`time`）：读取 `papers.fetched_at`，新论文得分更高，超过窗口后得分为 0。
5. 融合推荐（`fusion`，默认）：对所有算法结果做并集，缺失算法按 0 分，按配置相对权重归一化后加权平均排序。
6. 多种用法：支持 Python import 和 CLI。

## 2. 设计原则
1. 插件解耦：推荐算法与入口服务解耦，便于按需注册/替换。
2. 分数规范化：所有插件输出统一压缩到 `[0, 1]`。
3. 融合可解释：输出包含 `algorithm_scores`，可追踪每个算法对总分的贡献。
4. 容错可用：`fusion` 模式下单个插件失败不会导致整体失败。
5. 配置驱动：权重、时间窗口、默认算法、默认 top-k 全由 `config.yaml` 控制。

## 3. 配置项（config.yaml）
```yaml
paper_recommand:
  db_path: data/papers.db
  paper_table: papers
  activity_table: activity
  default_algorithm: fusion
  default_top_k: 20
  plugins:
    semantic:
      enabled: true
      top_k: 20
      weight: 1.0
    interaction:
      enabled: true
      like_weight: 0.45
      note_weight: 0.55
      dislike_penalty: 0.4
      recommended_penalty: 0.08
      weight: 1.0
    time:
      enabled: true
      freshness_window_days: 30
      weight: 1.0
```

字段说明：
1. `db_path`：sqlite 路径。
2. `paper_table`：论文元信息表，默认 `papers`。
3. `activity_table`：用户交互表，默认 `activity`。
4. `default_algorithm`：默认算法，推荐使用 `fusion`。
5. `default_top_k`：默认推荐条数。
6. `plugins.semantic.top_k`：语义推荐默认召回条数。
7. `plugins.<name>.weight`：fusion 中该插件的相对权重（代码内部自动归一化）。
8. `plugins.interaction.*`：交互推荐加减分权重。
9. `plugins.time.freshness_window_days`：时间推荐有效窗口天数。

## 4. 插件评分逻辑

### 4.1 semantic
1. 输入：`query`。
2. 流程：调用 `PaperEmbeddingService.search(query, top_k)`。
3. 打分：`score = 1 / (1 + distance)`，再 clamp 到 `[0,1]`。

### 4.2 interaction
1. 输入：`activity` 全表。
2. 加分：`like == 1` 增加 `like_weight`；有 `user_notes` 增加 `note_weight`。
3. 减分：`like == -1` 扣 `dislike_penalty`；每次历史推荐扣 `recommended_penalty`。
4. 输出：`score <= 0` 的论文不返回。

### 4.3 time
1. 输入：`papers.fetched_at`。
2. 打分：在 `freshness_window_days` 内按线性衰减，越新越高。
3. 超窗：超过窗口的论文得 0 分（不返回）。

## 5. Python API 使用
```python
from service.recommand import PaperRecommandService

service = PaperRecommandService()

# 1) 默认融合推荐
rows = service.recommend(top_k=10)

# 2) 指定语义推荐
semantic_rows = service.recommend(
    algorithm="semantic",
    query="large language model reasoning",
    top_k=5,
)

# 3) 指定交互推荐
interaction_rows = service.recommend(algorithm="interaction", top_k=10)

# 4) 指定时间推荐
recent_rows = service.recommend(
    algorithm="time",
    top_k=10,
    now="2026-03-12T00:00:00+00:00",
)

for item in rows:
    print(item.paper.id, item.score, item.algorithm_scores)
```

## 6. CLI 使用
脚本位置：`scripts/paper_recommand_cli.py`

1. 查看可用算法：
```bash
python scripts/paper_recommand_cli.py algorithms
```

2. 融合推荐（默认）：
```bash
python scripts/paper_recommand_cli.py recommend --top-k 10
```

3. 语义推荐：
```bash
python scripts/paper_recommand_cli.py recommend \
  --algorithm semantic \
  --query "large language model reasoning" \
  --top-k 5
```

4. 交互推荐：
```bash
python scripts/paper_recommand_cli.py recommend --algorithm interaction --top-k 10
```

5. 时间推荐：
```bash
python scripts/paper_recommand_cli.py recommend \
  --algorithm time \
  --top-k 10 \
  --now 2026-03-12T00:00:00+00:00
```

## 7. 关键数据模型
1. `models/paper_recommand.py#PaperRecommandRequest`
2. `models/paper_recommand.py#PaperRecommendation`

## 8. 测试
1. 单元测试：`tests/test_paper_recommand_unit.py`
2. 端到端测试：`tests/test_paper_recommand_e2e.py`

运行：
```bash
pytest -q tests/test_paper_recommand_unit.py tests/test_paper_recommand_e2e.py
```
