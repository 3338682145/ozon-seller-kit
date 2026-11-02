# 项目进度

更新时间：2026-11-02。正式执行环境：Supabase project eohvguguegxbhszvssbd。当前决策见DECISIONS.md，跨会话入口见HANDOFF.md。

## Supabase真实状态（最近一次SQL实查）
- PostgreSQL 17.6；schema：ozon_raw、ozon_analytics、ozon_meta。
- 原始12张表全部达到预期行数：合计466,767行，source_snapshot_id=toys_2026_11_02_33e5f029，状态imported_verified。
- 原始表唯一键检查通过：sku_snapshot_v2 29,823/29,823；keyword_sku的(keyword,sku) 177,063/177,063；fact_keyword_sku的(keyword,sku) 177,063/177,063。
- 历史分析结果上传进度：cluster_market_165=165/165；keyword_market_1642=1,642/1,642；cluster_sku_detail=40,757/40,757；keyword_sku_detail=12,000/177,060（上传中）；market_scale_summary=0/39（未上传）。
- 历史分析run_id=market_scale_v2_2026_11_02_70d6db0a，状态partial_historical_analytics_import。计数可能随上传变化，下一次运行必须重新查询。
- OMI-SYSTEM-1.0已注册Supabase prompt_registry；project_context保存当前目标、执行环境、实体层级、V2决策、资源清单、上下文恢复顺序和导入状态。
- 元数据表：source_snapshots、calculation_runs、project_context、decision_log、prompt_registry、run_events、artifact_registry、human_labels。新增6张上下文表已启用RLS；三个业务schema对anon/authenticated无USAGE权限。

## 系统架构文档
- [20-MASTER-SYSTEM-PROMPT.md](20-MASTER-SYSTEM-PROMPT.md)
- [21-RUNTIME-TOOLS-AND-RESOURCE-MANIFEST.md](21-RUNTIME-TOOLS-AND-RESOURCE-MANIFEST.md)
- [22-CONTEXT-PERSISTENCE-AND-HANDOFF.md](22-CONTEXT-PERSISTENCE-AND-HANDOFF.md)
- [23-RUN-PLAYBOOK.md](23-RUN-PLAYBOOK.md)
- [24-SUPABASE-IMPORT-STATUS-2026-11-02.md](24-SUPABASE-IMPORT-STATUS-2026-11-02.md)

## 项目建设状态
- [x] 原始12张表上传并逐表行数核验。
- [x] 原始核心唯一键检查通过。
- [x] 系统提示词、运行资源清单、上下文持久化机制建立。
- [x] Supabase元数据上下文表建立并写入当前决策。
- [x] 两张市场汇总表及cluster_sku_detail历史明细上传完成。
- [ ] keyword_sku_detail历史明细上传完成；market_scale_summary上传。
- [ ] 在Supabase创建新run_id，重新计算165簇/1,642关键词Gross、Net-est、GMV及双口径CR4。
- [ ] V2候选相似度、人工标注和验收。
- [ ] L2a精准同款/变体/跟卖Offer关系。
- [ ] Entry生产计算、利润ROI和30/60/90天预测回测。

## 红线
不把本地计算冒充Supabase计算；不覆盖原始快照；不将Net-est说成平台最终结算；不把1-redemptionRate称为退货率；不将CPC出价当实际广告扣费；不把需求簇当同款产品族；未验收V2不得覆盖V1。
