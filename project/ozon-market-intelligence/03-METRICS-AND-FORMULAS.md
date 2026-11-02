# 03 — 指标与计算公式

## 1. 需求与数据质量
Coverage = n_p6_joined / n_p8_items × 100。必须同时展示分子、分母、join失败原因。
Homogeneity = 主导三级类目SKU数 / 有效类目SKU数 × 100。
P7无行为率：>40%进入风险/排除；25–40%观察；<=25%较健康。zero_result_share单独报告。
关键词CR4 = 按sold_count排序的前4个不同SKU销量 / 该词所有可匹配SKU销量。仅代表p8前108位可观测样本。

## 2. 可打入性 Entry Score（优先级最高）
- max_slot30：position<=30内，单一seller_id占据的不同SKU最大数量。
- new_top10：top10中上架年龄<60天SKU数 / top10中有效create_date SKU数。
- p25_top10：top10有效挂牌价的第25百分位数，同时输出有效样本量。
- seller_id缺失单列unknown_seller_slots，不可当作不同卖家稀释霸屏。

B = 1 - MIN(max_slot30/10, 1)
N = MIN(new_top10/0.40, 1)
EntryScore = 100 × (0.60×B + 0.40×N)

分档：>=70货架较开放；50–70可测款；30–50进入成本偏高；<30货架壁垒高。max_slot30>5设强警告。p25_top10是价格压力指标，单独展示，不混入核心Entry，以免把价格竞争和货架可进入性混淆。

## 3. 机会评分
OpportunityScore = 0.50×EntryScore + 0.15×DemandScore + 0.10×GrowthScore + 0.15×ProfitScore + 0.05×CoverageScore + 0.05×P7QualityScore。

DemandScore = 100×MIN(LN(1+P7_count_28d)/LN(1+30000),1)。
GrowthScore = 100×CLAMP((weighted_growth_28d+20)/120,0,1)。
CoverageScore = 100×CLAMP(coverage/100,0,1)。
P7QualityScore = 100×(1-CLAMP(no_action_share/100,0,1))。

增长同时展示P7 dyn_7d、dyn_28d与Seerfar growth_30d；Seerfar异常增长评分前截断至100%。市场规模和EntryScore必须单独展示，不允许OpportunityScore替代原始指标。IP明确侵权、数据不可用、no_action_share>40%、严重红海等可设硬否决或人工复核。

## 4. 产品族市场规模
每个产品族分exact / close / broad三种范围。SKU先去重，再与同一快照p6关联。
MarketUnits28d = SUM(产品族去重SKU的sold_count)。
MarketGMV28d = SUM(产品族去重SKU的gmv_sum)。
MarketASP = MarketGMV28d / MarketUnits28d。
SellerCount = COUNT(DISTINCT seller_id)。
SKUShare = SKU.sold_count / MarketUnits28d。
FamilyCR4 = 产品族内销量前4个SKU销量 / MarketUnits28d。
Top1Share、Top4Share、SKU数、卖家数、样本覆盖率同时输出。

同SKU出现在多个关键词必须只计一次。不同件数、多件装、颜色或规格如果影响购买决策/价格，保留独立SKU，再汇总到父产品族。exact/close/broad不可混成单一数字。

## 5. 增速与趋势
有两期同口径p6快照时：SKU growth = (本期sold_count-上期sold_count)/上期sold_count；产品族增速按上期销量加权汇总。GMV、ASP同样分开计算。
无历史p6时，只报告P7搜索增长和Seerfar需求估算，标注“搜索需求增速”，不得称产品销量增速。
P7动态字段的统计定义需先确认是环比、同比还是平台动态指数。

## 6. 新品销量预测
对标样本限定候选关键词top10且产品形态一致，SKU去重。
ComparableMedian = 合格对标SKU的sold_count中位数；同时输出P25/P75、样本量。
初始情景系数仅作先验：保守0.15、基准0.27、乐观0.54。0.54是横截面追赶上限，不是承诺。
ScenarioUnits = ComparableMedian × scenario_factor，并受市场份额上限约束：ForecastUnits = MIN(ScenarioUnits, MarketUnits × share_cap)。初始share_cap可用0.5%/1%/2%作为试验假设，必须回测后校准。
ForecastGMV = ForecastUnits × MarketASP。
ForecastProfit = ForecastUnits × UnitProfit。
样本少于3个时降置信等级；新品预期应以对标样本分位数和历史新品爬坡曲线校准。

## 7. 单位经济、COGS上限与ROI
统一：P售价RUB，c佣金率，f平台/支付费率，d广告DRR，L跨境运费RUB，label贴标等RUB，C采购CNY，H国内运费包装CNY，E为RUB/CNY。

UnitProfit_RUB = P×(1-c-f-d) - L - label - E×(C+H)。
UnitMargin = UnitProfit_RUB / P。
UnitInvestment_CNY = C+H+(L+label)/E + P×(c+f+d)/E。
ROI = (UnitProfit_RUB/E) / UnitInvestment_CNY ×100%。
目标利润率m下：COGSmax_CNY = [P×(1-c-f-d-m)-L-label]/E - H。

佣金优先使用真实类目费率。selection-helper-local中的13/15/17价格档是估算，不可当真实佣金。其运费表可复用渠道、实重、体积重、计费档，但2026-04-15费率必须重新核价。不要重复扣除已经包含在GMV/实付价格中的项目。

## 8. 结单率和退货损耗
在业务定义验证前，模型保留两种情景：A按1-redemption_rate作为未成功结算率；B将其作为更广义未结单率，退货率另设参数。需要明确结单率的分子、分母、订单cohort、是否包含拒收/取消/配送失败。不要把结单率直接作为退货事实字段。