# 22 — 项目上下文持久化与跨会话 Handoff 规范

版本：OMI-CONTEXT-1.0

## 总原则
项目上下文不能依赖聊天记录或模型记忆。唯一可信状态由GitHub治理文档、Supabase元数据和数据表、Google Drive原始归档共同构成。新会话必须重新读取这些来源。

## 1. 各类内容保存在哪里

| 内容 | 权威保存位置 | 用途 |
|---|---|---|
| 原始Ozon数据行 | Supabase ozon_raw | 正式计算输入，按snapshot_id保留版本 |
| 原始数据库/Parquet文件 | Google Drive原始归档 | 原文件、SHA256、来源和修改日期留档 |
| 计算结果 | Supabase ozon_analytics | 按run_id版本化的市场规模、CR4、聚类、SKU族结果 |
| 数据快照信息 | Supabase ozon_meta.source_snapshots | 源文件、SHA256、日期、窗口、表行数、导入状态 |
| 计算运行记录 | Supabase ozon_meta.calculation_runs | 公式版本、参数、输入快照、运行状态、验证结果 |
| 项目当前状态 | GitHub PROJECT-STATUS.md | 哪些完成、哪些阻塞、下一步 |
| 已批准决策 | GitHub DECISIONS.md；同步Supabase decision_log | 决策内容、理由、批准状态和变更历史 |
| 系统提示词 | GitHub 20-MASTER-SYSTEM-PROMPT.md；同步Supabase prompt_registry | Agent行为规范及版本 |
| 每次运行事件 | Supabase ozon_meta.run_events | 阶段、SQL执行、错误、验证和时间 |
| 报告/导出物 | GitHub文档 + Google Drive归档；Supabase artifact_registry登记指纹和链接 | 报告、CSV、Excel、数据库导出 |
| 人工标注 | Supabase ozon_meta.human_labels；GitHub保留标注规范 | 聚类标签、复核结果、审计依据 |
| 下一轮交接 | GitHub HANDOFF.md；Supabase project_context保存当前handoff指针 | 新会话接续 |
| 临时工作文件 | 当前会话附件/沙箱 | 仅临时，不是权威来源 |

## 2. Supabase元数据表职责
已在ozon_meta建立：
- source_snapshots：每个原始数据版本的文件名、SHA256、大小、快照日期、窗口、表行数和状态。
- calculation_runs：每次计算的run_id、公式版本、输入快照、参数、验证结果和状态。
- project_context：当前项目关键上下文键值（JSONB）、版本、来源和更新时间。
- decision_log：机器可查询的决策历史；GitHub DECISIONS.md仍是人类可读主档。
- prompt_registry：系统提示词版本、正文、SHA256、启用状态。
- run_events：每次运行的阶段事件、错误、行数和校验载荷。
- artifact_registry：文件、报告、CSV、Excel、脚本的URI、GitHub链接、SHA256和验证状态。
- human_labels：关键词对的SAME_INTENT / RELATED_INTENT / DIFFERENT_INTENT人工标签。

所有元数据表位于私有ozon_meta schema；不得把数据库凭据写入这些上下文表。

## 3. 每次新会话如何恢复上下文
严格按以下顺序：
1. GitHub读取README.md。
2. 读取PROJECT-STATUS.md、DECISIONS.md、HANDOFF.md。
3. 读取20号系统提示词、21号运行资源清单。
4. 根据当前任务读取02数据契约、03公式、最新审计/计算报告和实验计划。
5. Supabase读取最新source_snapshots、calculation_runs、project_context、prompt_registry。
6. 查询当前任务相关raw/analytics表的实际行数与最新snapshot/run。
7. 将GitHub状态与Supabase实际状态比较；不一致时以Supabase实际数据状态为准，同时记录差异并更新GitHub。
8. 继续任务，不要求用户重复已经记录的决策。

## 4. 上下文更新规则
- 每次作出新决策：先确认用户明确批准，再追加DECISIONS.md和Supabase decision_log。
- 每次计算：生成run_id，写calculation_runs和run_events；保存输入、公式、参数、输出行数和验证。
- 每次新数据：创建新的snapshot_id，不覆盖旧snapshot；先校验SHA256和行数。
- 每次改系统提示词：升级prompt_version，旧版本retired，新版本active；记录SHA256和变更原因。
- 每次交付文件：登记artifact_registry；文件上传后读回核验，不得只凭上传响应宣称完成。
- 每次结束：更新PROJECT-STATUS和HANDOFF；写明已完成、未完成、阻塞、下一条具体动作。
- 每次GitHub修改后fetch_file读回；每次Supabase写入后execute_sql查询确认。

## 5. 不作为长期上下文的内容
- 聊天窗口中的临时对话、未确认推测、未验证数字。
- 模型自身的隐式记忆。
- 沙箱中的临时文件和未登记导出物。
- 没有snapshot_id/run_id的临时查询结果。
- 没有证据等级的人工估计。

本项目当前不依赖ChatGPT Memory作为事实库。即使未来启用，也只能作为便利提示，不能取代GitHub/Supabase记录。

## 6. 冲突处理
- 数据事实：Supabase实际表和snapshot优先于旧报告中的过期数字。
- 原始文件版本：SHA256不同即视为不同快照，不覆盖。
- 业务口径：最新经用户批准的DECISIONS记录优先；平台字段定义按官方UI/原始证据分级。
- 公式：以GitHub 03公式文档和Supabase calculation_runs formula_version为准。
- 若两个权威来源冲突：暂停受影响计算，记录冲突，不自行猜测。
