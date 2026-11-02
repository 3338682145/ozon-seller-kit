# Ozon Market Intelligence

版本 v1.4｜首个验证类目：解压玩具｜核心单位：产品族｜预测周期：30–90天

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

## 最新数据边界
新版toys.db有11张表，含P7、Seerfar、真实seller_id和100个商品级Seerfar详情样本。p8仅观测前108个搜索位，CR4为可观测样本口径。p6为28天窗口、快照2026-10-30；P7 count_28d为28天窗口、快照2026-10-29，窗口不能假设完全重合。旧版slim另含4,350条sku_weekly动态记录，新版toys.db不含该表，两者不可默认合并。

## 数据层建设状态
- [x] L1：165个需求词簇
- [x] L2：165个需求簇市场聚合
- [x] L3：48,898个唯一SKU实体
- [x] cluster-keyword 1,334条；cluster-SKU 40,759条；keyword-SKU 177,063条
- [ ] L2a：exact/close产品族与variant family
- [ ] Gross/net_est双口径市场规模和CR4重算
- [ ] max_slot30/new_top10生产流水线
- [ ] 类目佣金、物流、未结单损耗口径核准
- [ ] 连续历史快照与30–90天预测回测

## 最新字段口径
P6 soldCount/GMV是含取消退货的28天毛订单口径；nullableRedemptionRate是未取消且未退回比例，不能叫退货率；P6 salesDynamics是金额动态；P7 count_28d是独立搜索买家数，dyn基准仍待验证。DRR定义已确认，状态改为SEMANTICS_CONFIRMED / VALUE_QC_REQUIRED：可做批量分析但极端值质检，单品实际广告费优先账单/P8投放信息核对。

## 数据与治理红线
不得把搜索量当销量；不得把generalPopularity当销量；不得把p8前108位样本CR4称为全站CR4；不得跨关键词重复累计SKU；不得将估算净GMV说成平台最终结算收入；不得把1-redemption_rate直接当退货率；不得将CPC出价当实际扣费；不得跨类目套用23%人工佣金假设。RSI不得自动修改生产规则或执行采购/广告动作。