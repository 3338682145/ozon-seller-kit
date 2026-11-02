# 项目进度

更新时间：2026-11-02。正式执行环境：Supabase project eohvguguegxbhszvssbd。当前决策见DECISIONS.md，跨会话入口见HANDOFF.md。

## Supabase真实状态（最新SQL实查）
- PostgreSQL 17.6；schema：ozon_raw、ozon_analytics、ozon_meta。
- 原始12张表全部达到预期行数：合计466,767行，source_snapshot_id=toys_2026_11_02_33e5f029，状态imported_verified。
- 原始行数：blue_v3 142；category 1；dim_cluster 165；fact_keyword_sku 177,063；keyword_p7 9,979；keyword_score 2,795；keyword_seerfar 1,642；keyword_sku 177,063；product_seerfar 100；query_metrics_v2 1,642；sku_power 66,352；sku_snapshot_v2 29,823。
- 历史分析结果上传正在进行。最近核验：cluster_market_165=165；keyword_market_1642=1,642；cluster_sku_detail=24,000/40,757；keyword_sku_detail=0/177,060；market_scale_summary=0/39。行数可能随用户上传继续变化。
- 上述历史分析表关联run_id=market_scale_v2_2026_11_02_70d6db0a，状态partial_historical_analytics_import；不能当作完整导入或新一轮Supabase重算。
- 元数据表：source_snapshots、calculation_runs、project_context、decision_log、prompt_registry、run_events、artifact_registry、human_labels。
- OMI-SYSTEM-1.0已注册prompt_registry；project_context active keys=8（含当前导入状态）。
- 6张新增元数据表启用RLS；三个业务schema对anon/authenticated无USAGE权限。旧业务表RLS仍需后续纵深审查。

## 系统架构文档
- [20-MASTER-SYSTEM-PROMPT.md](20-MASTER-SYSTEM-PROMPT.md)
- [21-RUNTIME-TOOLS-AND-RESOURCE-MANIFEST.md](21-RUNTIME-TOOLS-AND-RESOURCE-MANIFEST.md)
- [22-CONTEXT-PERSISTENCE-AND-HANDOFF.md](22-CONTEXT-PERSISTENCE-AND-HANDOFF.md)
- [23-RUN-PLAYBOOK.md](23-RUN-PLAYBOOK.md)
- [24-SUPABASE-IMPORT-STATUS-2026-11-02.md](24-SUPABASE-IMPORT-STATUS-2026-11-02.md)

## 项目建设状态
- [x] 原始12张表上传并逐表行数核验。
- [x] 系统提示词、运行资源清单、上下文持久化机制建立。
- [x] Supabase元数据上下文表建立并写入当前决策。
- [ ] 历史计算结果明细上传完成并对账。
- [ ] 在Supabase创建新run_id，重新计算165簇/1,642关键词Gross、Net-est、GMV及双口径CR4。
- [ ] V2候选相似度、人工标注和验收。
- [ ] L2a精准同款/变体/跟卖Offer关系。
- [ ] Entry生产计算、利润ROI和30/60/90天预测回测。

## 红线
不把本地计算冒充Supabase计算；不覆盖原始快照；不将Net-est说成平台最终结算；不把1-redemptionRate称为退货率；不将CPC出价当实际广告扣费；不把需求簇当同款产品族；未验收V2不得覆盖V1。
