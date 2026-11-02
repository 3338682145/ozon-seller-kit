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


## 最新完成：P6/P7事实层（2026-11-02）
- run_id：`p6_p7_foundation_20261102_v1`；Supabase执行状态：completed_with_data_quality_warnings。
- P6：29,823 SKU唯一；Gross units 3,332,338；Net-est units 2,964,159.549；Gross GMV 1,318,910,734.23 RUB；Net GMV估算1,140,330,863.25 RUB；redemption缺失126。
- P7：9,979 query唯一；snap_date 2026-10-29；dyn_7d和dyn_28d各4个NULL，极端值保留raw。
- P8核心关键词到P7 query精确映射：560/1,642（34.10%）；1,082未匹配，不代表无需求。
- 新增表：ozon_analytics.fact_p6_sku_28d、fact_p7_keyword_28d、bridge_core_keyword_p7、p6_p7_quality_audit。四张表已启用RLS。
- 重要未决：P7 ca字段的实际值为double precision且范围0–78.87，与“加购人数”解释存在冲突；只保留ca_raw，未用于人数统计。P7 dyn比较基准未确认。
- 可复现SQL：project/ozon-market-intelligence/sql/build_p6_p7_foundation_v1.sql。
- 报告：26-P6-P7-FACT-LAYER-BUILD-REPORT-2026-11-02.md。

## 下一步
1. 核实P7 ca原生tooltip/接口单位和分母。
2. 对1,082个未精确匹配关键词做俄语规范化/别名候选召回与人工审核。
3. 基于P6/P7 facts构建统一keyword-market特征宽表，保留SKU/query粒度边界。
4. 再计算Seller CR4、max_slot30、new_top10和Entry。


## Ozon后台GMV截图核验
P6 category3_id=92811（抗压玩具）：28天Gross GMV 248,221,059 RUB；Net-est GMV 220,841,423 RUB；日均Gross 8,865,038 RUB。用户截图选中日2026-11-01显示10,107,993 RUB，比P6日均高14.02%，量级相符。截图右侧19,633,483 RUB指标口径不清，未用于核验。详情见27号报告。下一轮如要精确对账，需确认截图日期筛选范围及右侧指标tooltip。


## 重要范围修正：P6是跨类目混合池
P6 sku_snapshot_v2共29,823 SKU，覆盖22个category1和378个category3，并非全是抗压玩具。当前category3_id=92811的抗压玩具只有16,039 SKU（53.78%），28天Gross GMV 248,221,059 RUB（18.82%）；其余13,784 SKU贡献1,070,689,675 RUB Gross GMV（81.18%）。所以此前P6全表13.189亿RUB不得当成抗压玩具大盘。之后项目级核心市场默认筛选category3_id=92811；非抗压类目作为替代/邻近供给另行分析。详情见28-P6-CATEGORY-SCOPE-AUDIT-2026-11-02.md。
