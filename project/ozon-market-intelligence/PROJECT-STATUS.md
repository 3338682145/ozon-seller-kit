# 项目进度

更新时间：2026-11-02。正式执行环境：Supabase project eohvguguegxbhszvssbd。当前决策见DECISIONS.md，跨会话入口见HANDOFF.md。

## Supabase真实状态（本轮SQL实查）
- PostgreSQL 17.6；schema：ozon_raw、ozon_analytics、ozon_meta。
- 原始12张表已全部达到预期行数：合计466,767行，状态已在ozon_meta.source_snapshots标记为imported_verified。
- 原始表核对值：blue_v3 142；category 1；dim_cluster 165；fact_keyword_sku 177,063；keyword_p7 9,979；keyword_score 2,795；keyword_seerfar 1,642；keyword_sku 177,063；product_seerfar 100；query_metrics_v2 1,642；sku_power 66,352；sku_snapshot_v2 29,823。
- 分析结果表cluster_market_165、keyword_market_1642、cluster_sku_detail、keyword_sku_detail、market_scale_summary当前仍为0行；下一步在Supabase重算，不依赖本地历史结果作为生产结果。
- 元数据表已扩展：source_snapshots、calculation_runs、project_context、decision_log、prompt_registry、run_events、artifact_registry、human_labels。
- 已将OMI-SYSTEM-1.0系统提示词注册到Supabase prompt_registry；项目目标、环境、层级、V2决策和上下文恢复顺序已写入project_context。
- 6张新建元数据表已启用RLS；三个业务schema对anon/authenticated无USAGE权限。旧19张业务表仍需后续统一做RLS纵深审查，但当前schema为私有访问。

## 系统架构文件
- [20-MASTER-SYSTEM-PROMPT.md](20-MASTER-SYSTEM-PROMPT.md)：项目总系统提示词。
- [21-RUNTIME-TOOLS-AND-RESOURCE-MANIFEST.md](21-RUNTIME-TOOLS-AND-RESOURCE-MANIFEST.md)：每次运行可调用工具和必须读取的资源。
- [22-CONTEXT-PERSISTENCE-AND-HANDOFF.md](22-CONTEXT-PERSISTENCE-AND-HANDOFF.md)：上下文保存位置和跨会话恢复规则。
- [23-RUN-PLAYBOOK.md](23-RUN-PLAYBOOK.md)：标准启动、数据Gate、SQL执行、验证与交接流程。

## 项目建设状态
- [x] 原始12张表已上传Supabase并逐表行数核验。
- [x] 项目主系统提示词已建立并登记Supabase。
- [x] 每轮工具资源清单和上下文持久化机制已建立。
- [x] Supabase元数据表已扩展，记录决策、提示词、事件、文件和人工标签。
- [ ] 在Supabase重算165簇/1,642关键词Gross、Net-est、GMV及双口径CR4。
- [ ] 关键词聚类V2候选相似度计算、人工标注和验收。
- [ ] L2a精准同款/变体/跟卖Offer关系。
- [ ] Entry生产计算、利润ROI和30/60/90天预测回测。

## 当前计算运行
- source snapshot：toys_2026_11_02_33e5f029（imported_verified）。
- 历史计算run：market_scale_v2_2026_11_02_70d6db0a（awaiting_supabase_recompute）；其本地派生SQLite不是Supabase正式计算结果。
- 下一步应创建新的Supabase计算run_id，避免复用历史run。

## 红线
不把本地计算冒充Supabase计算；不覆盖原始快照；不将Net-est说成平台最终结算；不把1-redemptionRate称为退货率；不将CPC出价当实际广告扣费；不把需求簇当同款产品族；未验收V2不得覆盖V1。
