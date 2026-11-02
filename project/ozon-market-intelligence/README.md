# Ozon Market Intelligence

版本 v1.6｜首个验证类目：解压玩具｜核心单位：产品族｜预测周期：30–90天

## 项目目标
建立以Ozon市场交易与搜索数据为基础的产品级市场情报系统：识别真实大众需求，将同款SKU归并为产品族，计算市场规模、增速、竞争可进入性、单位经济与新品经营预期，并通过持续回测修正预测。

**决策顺序：需求真实性 → 产品族市场规模 → 可打入性 → 单位经济/ROI → 30–90天预测 → 实际结果回测。**

## 文档地图
1. [01 Goal与执行Plan](01-GOAL-AND-PLAN.md)
2. [02 数据字典与数据契约](02-DATA-CONTRACT.md)
3. [03 指标与计算公式](03-METRICS-AND-FORMULAS.md)
4. [04 数据核验与验收清单](04-VALIDATION-CHECKLIST.md)
5. [05 技术架构与数据流水线](05-TECHNICAL-ARCHITECTURE.md)
6. [06 RSI递归自我演进机制](06-RSI-SELF-IMPROVEMENT.md)
7. [07 里程碑与交付物](07-ROADMAP-AND-DELIVERABLES.md)
8. [08 SQLite初审报告](08-DATABASE-AUDIT-2026-11-02.md)
9. [09 完整版数据库更新审计](09-DATABASE-UPDATE-AUDIT-2026-11-02.md)
10. [10 数据归档与DRR质量政策](10-DATA-ARCHIVE-AND-DRR-POLICY.md)
11. [11 第二层产品需求簇与第三层SKU实体构建报告](11-LAYER-2-3-BUILD-REPORT.md)
12. [12 字段字典核验与模型口径修订](12-FIELD-DICTIONARY-VALIDATION-AND-MODEL-REVISION.md)
13. [13 项目进度、Goal差距与计算计划](13-PROGRESS-GAPS-AND-CALCULATION-PLAN.md)
14. [14 P6毛订单与估算妥投净规模试算](14-P6-GROSS-NET-SCALE-TRIAL.md)

## 当前数据与模型状态
- 数据层：L1 165个需求簇、L2簇-SKU聚合、L3 48,898个SKU实体和多对多桥表已构建；L2a exact/close产品族尚未完成。
- P6：28天gross下单口径含取消/退货；redemptionRate用于估算妥投净量；P6 salesDynamics是GMV动态。
- P7：count_28d是独立搜索买家数；dyn基准仍待连续快照验证。
- DRR：定义已确认，状态SEMANTICS_CONFIRMED / VALUE_QC_REQUIRED；异常值继续质检。
- Entry：max_slot30/new_top10需完成生产SQL/Python实现。
- 利润：佣金、物流重量尺寸、广告账单和未结单失败原因仍缺。
- 预测：需连续历史快照，30–90天模型尚未回测。

## 治理红线
不得把搜索量当销量；不得把generalPopularity当销量；不得把p8前108位样本CR4称为全站CR4；不得跨关键词重复累计SKU；不得将估算净GMV说成平台最终结算收入；不得把1-redemption_rate直接当退货率；不得将CPC出价当实际扣费；不得跨类目套用23%人工佣金假设。RSI不得自动修改生产规则或执行采购/广告动作。