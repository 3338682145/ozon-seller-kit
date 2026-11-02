# Handoff：Ozon Market Intelligence

## 新会话必读顺序
1. README.md
2. PROJECT-STATUS.md、DECISIONS.md、HANDOFF.md
3. 20-MASTER-SYSTEM-PROMPT.md
4. 21-RUNTIME-TOOLS-AND-RESOURCE-MANIFEST.md
5. 22-CONTEXT-PERSISTENCE-AND-HANDOFF.md
6. 23-RUN-PLAYBOOK.md
7. 按任务读取02-DATA-CONTRACT.md、03-METRICS-AND-FORMULAS.md及最新审计/实验报告
8. 查询Supabase source_snapshots、calculation_runs、project_context和原始表实际行数

## 权威环境
- Supabase project_id：eohvguguegxbhszvssbd；PostgreSQL 17.6。
- GitHub：3338682145/ozon-seller-kit。
- 正式计算只能在Supabase执行；GitHub记录规则、SQL、决策、报告和交接。
- Google Drive保留原始文件与归档；聊天和沙箱不作为长期事实库。

## 最新数据状态（2026-11-02 Supabase SQL实查）
原始12张表均已达到预期行数，合计466,767行：
blue_v3 142；category 1；dim_cluster 165；fact_keyword_sku 177,063；keyword_p7 9,979；keyword_score 2,795；keyword_seerfar 1,642；keyword_sku 177,063；product_seerfar 100；query_metrics_v2 1,642；sku_power 66,352；sku_snapshot_v2 29,823。
source_snapshot_id：toys_2026_11_02_33e5f029，状态imported_verified，源SHA256：33e5f02961c2782cead58e6714266aab6cbddc31e74242f905d2a7ba218502d8。

分析结果表当前为空；不要声称历史计算已经导入。下一步直接在Supabase重新计算并写入新的run_id。

## 元数据与上下文
- source_snapshots：原始文件指纹/行数/状态。
- calculation_runs：公式版本、输入快照、参数、校验。
- project_context：项目目标、执行环境、实体层级、V2决策和上下文恢复顺序。
- decision_log：已批准决策。
- prompt_registry：系统提示词版本。
- run_events：每次运行事件。
- artifact_registry：报告和导出物指纹/链接。
- human_labels：聚类人工标注。

已注册系统提示词版本：OMI-SYSTEM-1.0。GitHub主文档为20-MASTER-SYSTEM-PROMPT.md。

## 当前下一步
1. 在Supabase先做唯一键、空值、关联率和源快照完整性Gate。
2. 新建run_id，重算165需求簇和1,642关键词Gross/Net-est、GMV和CR4双口径。
3. 对账P8 position 1–108、跨簇SKU全局去重和结单率缺失覆盖。
4. 结果写ozon_analytics；run_events/calculation_runs写验证和耗时。
5. GitHub新增结果报告并读回，更新PROJECT-STATUS和HANDOFF。
6. 然后执行V2候选对相似度计算。

## 业务口径
P6毛订单含取消退货；Net-est按nullableRedemptionRate估算，NULL不填补；P6 salesDynamics是GMV动态；P7 count_28d是独立搜索买家数；P8只用position 1–108；CR4是可观测SKU样本；DRR定义已确认但数值需QC；V1冻结，V2为搜索意图聚类，L2a同款/跟卖独立建设。
