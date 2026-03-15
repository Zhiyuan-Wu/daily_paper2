# Daily Paper 2 静态 Code Review 报告

## 1. 审查范围与方法
1. 审查范围：`service/`、`website/backend/`、`website/frontend/`、`scripts/`、`skills/`、`docs/`、`tests/`。
2. 检查维度：总体原则一致性、架构与设计合理性、算法正确性、逻辑矛盾、实现完整性、Bug/性能/可扩展性、代码规范、实现-文档一致性、测试完整性。
3. 执行验证：
- `pytest -m 'not e2e' -q`：`25 passed, 2 skipped, 7 deselected`
- `cd website/frontend && npm run test`：`2 passed`

## 2. 总体结论
1. 平台基础能力完整，可运行并通过当前单测基线。
2. 但存在若干高风险问题，集中在：
- 后端安全边界（任意文件读取、无鉴权触发高权限任务）
- 向量增量算法正确性（会漏算）
- 技能流程可执行性（关键 SQL 写错字段）
3. 同时存在明显技术债：动态 SQL 约束不足、前端页面重复度高、性能扩展路径薄弱、测试对关键边界覆盖不足。

## 3. 关键问题清单（按严重级别）

### 严重级（Critical）

#### C1. Markdown 文件读取存在路径穿越/任意文件读取风险
- 位置：`website/backend/api.py:237`、`website/backend/api.py:245`、`website/backend/api.py:247`
- 证据：`_read_markdown_file()` 直接使用数据库中的 `local_md_path/ai_report_path`，仅做 `exists/is_file` 判断，未限制必须位于白名单目录，也未做 `resolve()` 后的根路径约束。
- 影响：若数据库路径字段被污染，可读取服务进程可访问的任意文件（配置、密钥、源码等）。
- 与原则冲突：违背平台安全可运维原则。
- 建议：
1. 对路径执行 `resolved = path.resolve()`。
2. 强制 `resolved.is_relative_to(allowed_root)`（或等价逻辑）。
3. 拒绝绝对路径输入，仅允许受控相对路径。
4. 为该路径边界增加单元与 API 测试。

#### C3. Embedding 增量同步算法存在漏算缺陷
- 位置：`service/embedding/embedding_service.py:94`、`service/embedding/repository.py:159`
- 证据：增量条件使用 `fetched_at > latest.max_fetched_at`。
- 影响：
1. 同一 `fetched_at` 下若上次因 `limit` 未处理完，剩余记录永久漏算。
2. 晚到/回填的旧时间戳论文也会漏算。
- 与原则冲突：与“增量优先且可追踪”目标冲突，语义检索结果不完整。
- 建议：
1. 改为水位线 `(fetched_at, paper_id)` 复合游标。
2. 条件改为 `fetched_at > last_ts OR (fetched_at = last_ts AND id > last_id)`。
3. 增加针对“同时间戳+limit分页”的回归测试。

### 高级（High）

#### H1. 技能工作流 SQL 字段错误，导致流程判断失真
- 位置：`skills/paper-analysis/SKILL.md:82`、`skills/paper-analysis/SKILL.md:88`
- 证据：查询 `paper_parses` 时使用 `WHERE id = '$PAPER_ID'`，而表字段是 `paper_id`。
- 影响：解析状态检查可能始终失败，触发重复解析或错误分支，工作流不可靠。
- 建议：统一改为 `WHERE paper_id = ...`，并对技能脚本增加最小可执行自检步骤。

#### H2. 多处动态 SQL 表名未做白名单校验
- 位置：`service/activity_management/repository.py:36`、`service/embedding/repository.py:73`、`service/recommand/repository.py:54`
- 证据：表名由配置/参数进入 f-string SQL，缺少统一正则校验（仅 `report` 模块做了校验）。
- 影响：配置被污染时可能出现 SQL 注入/DDL 破坏风险；也增加运维误配置故障概率。
- 建议：抽取统一 `validate_table_name()`，所有仓储模块强制校验。

#### H3. 语义检索实现为全表距离排序，扩展性不足
- 位置：`service/embedding/repository.py:271`、`service/embedding/repository.py:275`
- 证据：`vec_distance_cosine(e.embedding, ?)` + `ORDER BY distance LIMIT ?`，在普通表上做全量距离计算。
- 影响：数据规模增大后查询延迟和 CPU 成本线性增长，难以支撑高并发。
- 建议：使用 sqlite-vec 推荐的向量索引/虚拟表方案，或引入专用向量检索层。

### 中级（Medium）

#### M1. 时间推荐插件每次全量拉取论文，存在性能瓶颈
- 位置：`service/recommand/plugins/time_decay.py:24`、`service/recommand/repository.py:54`
- 影响：推荐请求复杂度随总论文数线性增长，`top_k` 无法提前截断计算。
- 建议：增加一个固定的截止时间窗口30天（可配置）

#### M2. `PaperFetch` 缺少 `limit` 正数校验
- 位置：`service/fetch/paper_fetch.py:135`、`service/fetch/sources/arxiv_source.py:70`
- 影响：`limit<=0` 时可能触发源插件异常或无意义请求，行为不确定。
- 建议：入口统一校验 `limit >= 1`。


#### M4. 设置页日志轮询 effect 依赖 `logOffset`，导致定时器频繁重建
- 位置：`website/frontend/src/pages/SettingsPage.tsx:157`、`website/frontend/src/pages/SettingsPage.tsx:196`
- 影响：轮询逻辑抖动，可能产生重复请求/额外开销，维护复杂。
- 建议：用 `useRef` 持有 offset，effect 只依赖 `selectedTaskId`。

#### M5. 前端页面重复度高且实现不一致
- 位置：`website/frontend/src/pages/DailyReportPage.tsx`（448 行）、`website/frontend/src/pages/PaperExplorePage.tsx`（419 行）、`website/frontend/src/pages/DailyReportPage.tsx:418`、`website/frontend/src/pages/PaperExplorePage.tsx:390`
- 证据：详情弹窗、AI解读、笔记、like 逻辑大段重复；日报页用原生 `<textarea>`，探索页用 `Input.TextArea`。
- 影响：改动容易漂移，缺陷修复需多点同步。
- 建议：抽取共享 hooks/components（如 `usePaperActions`、`PaperDetailModal`、`NoteModal`）。

#### M8. “过度兼容/重复代码”技术债明显
- 位置：`service/*/config.py`（多处重复 `load_app_config`）、`service/*/__init__.py`（大量别名）
- 影响：维护成本高，配置解析行为难以统一演进。
- 建议：统一配置加载器与校验工具，不做别名兼容

### 低级（Low）

#### L1. 文档与实现不一致（前端状态目录）
- 位置：`CLAUDE.md:131`、`website/frontend/src/store/uiStore.ts:1`
- 证据：文档写 `src/stores/`，实际是 `src/store/`。
- 影响：新开发者定位成本增加。
- 建议：修正文档。

