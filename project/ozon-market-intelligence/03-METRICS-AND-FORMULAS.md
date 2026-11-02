# 03 — 指标与计算公式（按2026-11-02字段字典修订）

## 1. 需求与数据质量
Coverage = n_p6_joined / n_p8_items × 100；必须展示分子、分母和join失败原因。
Homogeneity = 主导三级类目SKU数 / 有效类目SKU数 ×100。
P7 no_action_share是搜索后无点击查询占比，不等于假需求；zr_share是未找到合适商品的查询占比，代表潜在供给缺口。两者分开分析。
P7 count_28d是过去28天搜索过商品的独立买家数，不是搜索次数；ca/ord是加购/下单独立买家数，conv_to_cart/conv_pct是买家比例。跨关键词累加人数可能重复，不得称去重消费者总量。

## 2. P6毛订单与估算妥投净量
P6 soldCount为28天订购商品件数，含取消和退货；gmvSum/soldSum同样是毛订单金额，含取消和退货。
r = nullableRedemptionRate / 100。该字段定义为未取消且未退回订单商品占比（成功结单率），不是退货率。
U_gross = soldCount
U_net_est = soldCount × r
P = avgPrice = gmvSum / soldCount
GMV_net_est = U_net_est × P

net_est是按毛订单平均价估算的妥投净GMV，不是平台直接给出的最终结算收入；需同时展示gross与net_est，并说明价格结构假设。

## 3. CR4双口径
CR4_gross = 毛订单销量Top4之和 / 全部可匹配SKU毛订单销量。
CR4_net_est = 估算妥投净销量Top4之和 / 全部可匹配SKU估算妥投净销量。
两种口径分别重新排序Top4。分母仅限P8前108位可观测且成功匹配P6的SKU，不是全站完整市场。
generalPopularity是综合行为热度，不是销量，严禁用于CR4。

## 4. 可打入性
max_slot30 = position<=30中，按seller_id统计不同SKU数量的最大值。
new_top10 = top10中上架不足60天且create_date有效的SKU数 / top10中create_date有效的SKU数。
B = 1 - MIN(max_slot30/10,1)
N = MIN(new_top10/0.40,1)
EntryScore = 100 × (0.60×B + 0.40×N)
注意：字段齐备，但 DATA-VERIFICATION-12-ITEMS 记载原仓库尚未实现可复算生产代码。上线前需补SQL/Python测试和快照日期边界测试。

## 5. 产品族市场规模
SKU先通过L2a产品族映射并DISTINCT去重，再分别汇总gross_units、net_units_est、gross_gmv、net_gmv_est、ASP、seller_count、Top1/Top4份额。Exact/close/broad分开。SKU跨多个需求簇可分别参与需求簇分析，但跨簇总市场必须全局去重。

## 6. 库存校正
avgOrdersOnAccDays为含取消/退货的有货日平均毛订单件数；×28可作假设全28天有货时的毛需求运行率。avgGmvOnAccDays同理。它们不是净销量。sumMissedGmv为缺货机会损失，单列，不加入实际GMV。stock/fboStock/fbsStock是周期末后台库存申报值。
买家端stock_max每日下降可作为库存消耗代理，但补货、仓间调拨、购买上限2000等会干扰，未经校准不能当作真实销售。

## 7. 增速
P6 salesDynamics是订单金额动态，不是件数动态。
P7 dyn_7d/dyn_28d比较基准尚未确认；与Seerfar growth_30d相关但不等值，连续快照验证前只标平台动态指数。
产品真实净销量增长需要连续同口径P6快照：(本期U_net_est-上期U_net_est)/上期U_net_est。
旧版sku_weekly仅在确认统计窗口和日期后用于动量特征，不替代真实时间序列。

## 8. 单位经济与ROI
P6 gross GMV含取消/退货，先计算net_est收入，再根据佣金、支付费、物流、广告、采购和包装成本建情景模型。
DRR定义为推广费用/毛订单价值，分母含取消退货，按价格上限计算；其语义已确认，但极端值需质量控制。drr=0保留为0值，daysWithTrafarets辅助核验。单SKU优先核查P8推广状态和CPC/CPO出价；CPC是出价不是实际扣费。广告真实费用最好以账单对账。
佣金23%是人工假设，不能跨类目套用。物流按当前有效费率、重量/体积重计算；P6只有volume，重量尺寸需另采。
redemption_rate不是return_rate；未成功结单的失败原因（取消、拒收、未取件、退货等）需拆分，不能把1-r直接当退货率和逆向物流成本。

## 9. 证据与版本
所有派生字段记录formula_version、computed_at、snapshot_id、源字段与估算标记。官方UI解释、接口实测、工程假设分级保存。


## 10. P6/P7事实层实施口径（2026-11-02）
Supabase正式事实层：
- `ozon_analytics.fact_p6_sku_28d`：SKU×28天快照；Gross按raw sold_count，Net-est按gross_units×redemption_rate_pct/100；结单率NULL时Net保持NULL；Net GMV按Net-est件数×P6 avg_price估算。
- `ozon_analytics.fact_p7_keyword_28d`：query×28天快照；count_28d按query保留独立搜索买家数；跨query不得加总为全市场独立消费者。
- `ozon_analytics.bridge_core_keyword_p7`：P8核心关键词与P7 query映射；当前只做精确字符串匹配，未匹配不代表零需求。
- `ozon_analytics.p6_p7_quality_audit`：每次构建的行数、NULL、范围和语义警告。

当前run_id：`p6_p7_foundation_20261102_v1`；source_snapshot_id：`toys_2026_11_02_33e5f029`。

P7语义警告：
- dyn_7d/dyn_28d的比较基准未核实，保留raw，不作为标准环比或销量增长；本快照各有4个NULL，且存在极端值。
- ca字段历史解释为加购人数，但当前数据类型为double precision、实际范围0–78.87，存在单位/分母不一致。本版只保存ca_raw，不按人数解释、不求和，待Ozon原生tooltip/接口复核。
- no_action_share是搜索无点击比例，不等于假需求；zr_share是零结果占比，可作为供给缺口信号。

详见[26-P6-P7事实层构建报告](26-P6-P7-FACT-LAYER-BUILD-REPORT-2026-11-02.md)。
