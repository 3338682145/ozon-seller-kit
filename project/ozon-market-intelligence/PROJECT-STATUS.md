# 项目进度

更新时间：2026-11-02。正式执行环境：Supabase project eohvguguegxbhszvssbd。当前决策见DECISIONS.md，跨会话入口见HANDOFF.md。

## Supabase真实状态（本轮只读SQL实查）
- PostgreSQL 17.6.1.166；schema：ozon_raw、ozon_analytics、ozon_meta。
- 原始12张表合计466,767行；snapshot_id=toys_2026_11_02_33e5f029；每张raw表均只有该snapshot_id。
- 源文件SHA256=33e5f02961c2782cead58e6714266aab6cbddc31e74242f905d2a7ba218502d8。
- 核心唯一键通过：sku_snapshot_v2 29,823/29,823；keyword_sku(keyword,sku) 177,063/177,063；fact_keyword_sku(keyword,sku) 177,063/177,063。
- 历史分析表已全部上传：cluster_market_165=165；keyword_market_1642=1,642；cluster_sku_detail=40,757；keyword_sku_detail=177,060；market_scale_summary=39。
- 历史导入run_id=market_scale_v2_2026_11_02_70d6db0a，calculation_version=market-scale-v2-strict-p8-top108，状态为imported；这不是本轮新建的生产计算run。
- 只读对账：1642个关键词聚合与raw重算0项差异；165个簇聚合0项差异；cluster_sku_detail集合和值0项差异；keyword_sku_detail有效position全覆盖，已匹配且结单率有效的143,720条Net值在浮点容差内一致；market_scale_summary中14项核心指标通过对账。
- 本轮未创建新run_id，未修改raw、analytics、权限或表结构。

## 最新数据缺口
- P6：redemption_rate缺失126（0.42%）；create_date缺失105（0.35%）；volume缺失3（0.01%）；sales_dynamics缺失7,516（25.20%）。
- P8：177,060条position 1–108有效记录；48,896个不同SKU中29,821个匹配P6，19,075个不匹配；rating/reviews各34,499条NULL；relevance全空；推广中记录CPC缺失32,163/114,423（28.11%）。
- P7：9,979条query主要需求字段无NULL；dyn_7d/dyn_28d各4条NULL；1642个核心关键词中仅560个与P7精确匹配。
- 需求簇：165簇覆盖1,334个关键词；308个核心关键词未分配，fact_keyword_sku有33,204条cluster_id为NULL。
- L2a：没有产品族映射表；product_seerfar仅100条样本，但raw_json含weight/dimension/volume/variants/variationIds。
- 利润：缺采购报价、MOQ、国内运费、物流费率、平台佣金/支付费率、实际广告账单、税费和取消/退货原因明细。
- 预测：目前只有一个raw快照，不能训练可靠30/60/90天时间序列模型。
- 详见[25数据缺口审计](25-DATA-GAP-AUDIT-2026-11-02.md)。

## 性能与安全
- 12张raw表没有索引/主键；现有索引主要为analytics/meta主键。旧rebuild_market_scale.py采用SQLite+Pandas多轮merge和分组循环，需改为Supabase集合式SQL。
- Supabase表清单提示19张raw/analytics/meta表未启用RLS；但本轮SQL确认anon/authenticated对三个业务schema均无USAGE权限，且对ozon_raw.keyword_sku无SELECT权限。仍需设计RLS策略，不能无策略直接启用。
- 本轮没有执行索引DDL、RLS变更或其他生产结构修改。

## 系统架构文档
- [20-MASTER-SYSTEM-PROMPT.md](20-MASTER-SYSTEM-PROMPT.md)
- [21-RUNTIME-TOOLS-AND-RESOURCE-MANIFEST.md](21-RUNTIME-TOOLS-AND-RESOURCE-MANIFEST.md)
- [22-CONTEXT-PERSISTENCE-AND-HANDOFF.md](22-CONTEXT-PERSISTENCE-AND-HANDOFF.md)
- [23-RUN-PLAYBOOK.md](23-RUN-PLAYBOOK.md)
- [24-SUPABASE-IMPORT-STATUS-2026-11-02.md](24-SUPABASE-IMPORT-STATUS-2026-11-02.md)
- [25-DATA-GAP-AUDIT-2026-11-02.md](25-DATA-GAP-AUDIT-2026-11-02.md)

## 项目建设状态
- [x] 原始12张表上传并逐表行数核验。
- [x] 原始核心唯一键检查通过。
- [x] 历史5张分析表上传完整。
- [x] 关键词、需求簇、SKU明细及核心市场汇总与raw只读对账。
- [x] Supabase数据资产、NULL、关联率、时间序列、成本和性能缺口审计。
- [ ] 在Supabase创建新run_id，正式重算165簇/1,642关键词Gross、Net-est、GMV及双口径CR4。
- [ ] 设计并测量raw表索引与集合式SQL计算流程。
- [ ] 修复P7 query映射和308个未分配关键词的归因（V1保持冻结）。
- [ ] L2a精准同款/变体/跟卖Offer关系。
- [ ] Entry生产计算、供应链成本/利润ROI。
- [ ] 连续P6/P7快照与30/60/90天预测回测。

## 红线
不把本地计算冒充Supabase计算；不覆盖原始快照；不将Net-est说成平台最终结算；不把1-redemptionRate称为退货率；不将CPC出价当实际广告扣费；不把需求簇当同款产品族；未验收V2不得覆盖V1。


## 2026-11-02 P6/P7事实层构建完成
- 新run_id：`p6_p7_foundation_20261102_v1`；状态：completed_with_data_quality_warnings。
- P6事实表：`ozon_analytics.fact_p6_sku_28d`，29,823行、SKU唯一；Gross销量3,332,338；Net-est销量2,964,159.549；Gross GMV 1,318,910,734.23 RUB；Net GMV估算1,140,330,863.25 RUB；结单率缺失126，Net覆盖率99.5775%。
- P7事实表：`ozon_analytics.fact_p7_keyword_28d`，9,979行、query唯一，快照2026-10-29；dyn_7d和dyn_28d各4个NULL，极端值保留原值。
- 核心词映射：`bridge_core_keyword_p7` 1,642行；精确匹配560（34.10%），未精确匹配1,082；未匹配不代表无需求，暂未做模糊匹配。
- 质量审计：`p6_p7_quality_audit` 3行；新建4张表已启用RLS。
- P7 ca单位与分母存在歧义，本轮仅存ca_raw；dyn比较基准未确认，均不得直接作为正式指标。
- 可复现SQL：`sql/build_p6_p7_foundation_v1.sql`；报告：[26-P6-P7-FACT-LAYER-BUILD-REPORT-2026-11-02.md](26-P6-P7-FACT-LAYER-BUILD-REPORT-2026-11-02.md)。


## Ozon后台GMV交叉核验（2026-11-02）
- 类目：抗压玩具，category3_id=92811。
- P6 28天：16,039 SKU；Gross GMV 248,221,059 RUB；Net GMV估算220,841,423 RUB；Gross日均8,865,038 RUB。
- 用户截图选中日显示10,107,993 RUB，较P6日均高14.02%，数量级相符；结论为合理性核验，不是逐日精确对账。
- 右侧19,633,483 RUB指标统计窗口/定义未确认，暂不用于对账。
- 详情：[27-ANTISTRESS-GMV-SCREENSHOT-RECONCILIATION-2026-11-02.md](27-ANTISTRESS-GMV-SCREENSHOT-RECONCILIATION-2026-11-02.md)。


## P6类目范围审计（2026-11-02）
- 发现P6 sku_snapshot_v2不是纯抗压玩具样本，而是跨类目混合池：29,823 SKU覆盖22个category1、378个category3。
- 当前category3_id=92811（抗压玩具）：16,039 SKU（53.78%），28天Gross GMV 248,221,059 RUB（18.82%），Gross销量1,117,485件。
- 非抗压玩具：13,784 SKU（46.22%），28天Gross GMV 1,070,689,675 RUB（81.18%）。category3_id无NULL。
- 因此此前P6总池13.189亿RUB是混合类目GMV，不能称为抗压玩具市场规模。抗压玩具当前可观测28天Gross GMV约2.482亿RUB，Net-est约2.208亿RUB。
- 后续项目默认scope必须显式限定category3_id=92811；外部类目只作为替代品/相邻市场分析，不并入核心分母。报告：[28-P6-CATEGORY-SCOPE-AUDIT-2026-11-02.md](28-P6-CATEGORY-SCOPE-AUDIT-2026-11-02.md)。
