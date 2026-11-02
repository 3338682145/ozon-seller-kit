# Handoff：Ozon Market Intelligence

## 新会话必读顺序
1. README.md
2. PROJECT-STATUS.md、DECISIONS.md、HANDOFF.md
3. 20-MASTER-SYSTEM-PROMPT.md
4. 21-RUNTIME-TOOLS-AND-RESOURCE-MANIFEST.md
5. 22-CONTEXT-PERSISTENCE-AND-HANDOFF.md
6. 23-RUN-PLAYBOOK.md、24-SUPABASE-IMPORT-STATUS-2026-11-02.md
7. 按任务读取02数据契约、03公式和最新实验/审计报告
8. 查询Supabase source_snapshots、calculation_runs、project_context和当前表行数

## 权威环境
Supabase project_id=eohvguguegxbhszvssbd，PostgreSQL 17.6。正式计算只能在Supabase执行。GitHub保存系统提示词、SQL、规则、进度、决策、报告和handoff；Google Drive保存原始文件和归档；聊天和沙箱不是长期事实库。

## 最新原始数据状态
toys.db SHA256=33e5f02961c2782cead58e6714266aab6cbddc31e74242f905d2a7ba218502d8。12张原始表已全部达到预期行数，合计466,767行。snapshot_id=toys_2026_11_02_33e5f029，状态imported_verified。

## 历史分析结果上传状态（2026-11-02最近核验）
- cluster_market_165：165/165
- keyword_market_1642：1,642/1,642
- cluster_sku_detail：24,000/40,757（部分）
- keyword_sku_detail：0/177,060
- market_scale_summary：0/39
这些历史分析结果仍在上传/未完整对账，run_id=market_scale_v2_2026_11_02_70d6db0a，状态partial_historical_analytics_import。重新开始任务时必须重查行数。

## 系统提示词和上下文
OMI-SYSTEM-1.0主档：20-MASTER-SYSTEM-PROMPT.md；已注册Supabase ozon_meta.prompt_registry。
工具清单：21-RUNTIME-TOOLS-AND-RESOURCE-MANIFEST.md。
上下文存储：22-CONTEXT-PERSISTENCE-AND-HANDOFF.md。
标准执行：23-RUN-PLAYBOOK.md。
导入核验：24-SUPABASE-IMPORT-STATUS-2026-11-02.md。

## 下一步
1. 等待/核验历史分析表上传完成；但不把它当作正式生产计算。
2. 对原始表做唯一键、NULL、关联率和快照一致性Gate。
3. 创建新的run_id，在Supabase重新计算Gross/Net-est、GMV、SKU CR4和Seller CR4。
4. 写入ozon_analytics及run_events，完成行数、公式和历史baseline对账。
5. 再启动V2候选关键词对计算和人工标注。

## 业务口径
P6毛订单含取消/退货；Net-est按nullableRedemptionRate估算，NULL不填补；P6 salesDynamics是GMV动态；P7 count_28d是独立搜索买家数；P8 position 1–108；CR4为可观测SKU样本；DRR定义已确认但数值仍QC；V1冻结，V2为搜索意图聚类，L2a同款/跟卖独立建设。
