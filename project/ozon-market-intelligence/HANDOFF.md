# Handoff：Ozon Market Intelligence

## 新会话必读顺序
1. README.md
2. PROJECT-STATUS.md、DECISIONS.md、HANDOFF.md
3. 20-MASTER-SYSTEM-PROMPT.md
4. 21-RUNTIME-TOOLS-AND-RESOURCE-MANIFEST.md
5. 22-CONTEXT-PERSISTENCE-AND-HANDOFF.md
6. 23-RUN-PLAYBOOK.md、24-SUPABASE-IMPORT-STATUS-2026-11-02.md、25-DATA-GAP-AUDIT-2026-11-02.md
7. 按任务读取02数据契约、03公式和最新实验/审计报告
8. 查询Supabase source_snapshots、calculation_runs、project_context和当前表行数

## 权威环境
Supabase project_id=eohvguguegxbhszvssbd，PostgreSQL 17.6。正式计算只能在Supabase执行。GitHub保存系统提示词、SQL、规则、进度、决策、报告和handoff；Google Drive保存原始文件和归档；聊天和沙箱不是长期事实库。

## 原始数据
toys.db SHA256=33e5f02961c2782cead58e6714266aab6cbddc31e74242f905d2a7ba218502d8。12张原始表合计466,767行；每张表只有snapshot_id=toys_2026_11_02_33e5f029。核心唯一键检查通过。

## 历史分析结果（本轮SQL实查）
- cluster_market_165：165/165
- keyword_market_1642：1,642/1,642
- cluster_sku_detail：40,757/40,757
- keyword_sku_detail：177,060/177,060
- market_scale_summary：39/39
关联run_id=market_scale_v2_2026_11_02_70d6db0a，状态imported。只读对账已通过核心指标检查；尚未创建新的生产计算run_id。

## 最新数据缺口
完整报告：25-DATA-GAP-AUDIT-2026-11-02.md。
关键缺口：P8有19,075个不同SKU未匹配P6；308个核心关键词未分配需求簇；P7与1642核心词精确匹配560个；无L2a产品族映射及全量Seller Offer；缺采购成本/物流费率/实际广告账单；只有单期快照，无法可靠预测；raw表没有索引，旧Python/Pandas流程应替换为Supabase集合式SQL。

## 下一步执行顺序
1. 先设计Supabase SQL集合式计算和索引方案，使用EXPLAIN (ANALYZE, BUFFERS)建立基准；本轮未执行任何DDL。
2. 创建新的唯一run_id，在Supabase基于raw重算Gross/Net-est、GMV、SKU CR4和Seller CR4；与历史baseline对账。
3. 修复P7关键词映射及308个未分配关键词的归因，V1 165簇保持冻结。
4. 从product_seerfar现有raw_json提取100条样本的变体、重量和尺寸，再决定高价值SKU补采范围。
5. 采集L2a所需商品身份、全量变体和Seller Offer证据。
6. 获取采购报价、物流费率、平台佣金、广告账单等成本数据。
7. 建立连续P6/P7快照后再训练和回测30/60/90天预测。

## 业务口径
P6毛订单含取消/退货；Net-est按nullableRedemptionRate估算，NULL不填补；P6 salesDynamics是GMV动态；P7 count_28d是独立搜索买家数；P8 position 1–108；CR4为可观测SKU样本；DRR定义已确认但数值仍QC；V1冻结，V2为搜索意图聚类，L2a同款/跟卖独立建设。
