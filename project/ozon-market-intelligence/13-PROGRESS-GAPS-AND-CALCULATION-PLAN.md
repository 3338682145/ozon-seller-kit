# 13 — 项目进度、Goal差距与当前计算体系（2026-11-02）

## 总体判断
项目已完成数据源审计、L1需求词簇、L2需求簇市场聚合、L3 SKU实体及关联桥表第一版；字段字典已核验并修订毛订单/估算妥投净口径。当前仍不是可直接给出可靠新品ROI和30–90天预测的生产系统。

## Goal对照
| Goal模块 | 当前状态 | 已完成 | 主要差距 |
|---|---|---|---|
| 市场大盘 | 部分完成 | 165需求簇、簇内SKU去重聚合、毛订单销量/GMV | 需重算net_est；跨簇去重；p8只覆盖前108位 |
| 产品识别 | 部分完成 | 48,898 SKU实体、关键词/簇关联 | L2a exact/close产品族缺失；变体关系不全 |
| 可打入性 | 规则已定义、生产实现未完成 | max_slot30/new_top10字段可用，少量样例 | 需可复算SQL/Python、全量重算、测试 |
| 经营利润 | 未完成 | 已明确毛/净估算口径，DRR定义已核验 | 类目佣金、重量尺寸、物流费率、广告账单、失败订单成本不足 |
| 趋势预测 | 未完成 | P7需求快照、旧slim sku_weekly动量数据 | 缺连续同口径历史快照，P7 dyn语义未确认 |
| RSI | 设计完成，运行闭环未完成 | 版本化、回测、影子运行、人工审批方案 | 缺预测-实际结果表和自动回测作业 |

## 字段口径关键修订
- P6 soldCount与gmvSum是28天毛订单口径，含取消/退货。
- r=nullableRedemptionRate/100，定义为未取消且未退回的订单商品比例。
- U_net_est=soldCount×r；GMV_net_est=U_net_est×avgPrice。均为估算妥投口径，不是平台最终结算金额。
- 1-r是未结单比例，不是退货率。
- P6 salesDynamics是订单金额动态，不是销量增速。
- P7 count_28d是独立搜索买家数；ca/ord为独立加购/下单买家数；dyn_7d/dyn_28d精确比较基准未知。
- P8 generalPopularity不是销量；CPC/CPO是出价，不等于实际广告扣费。
- DRR定义已确认，但极端值仍须质量控制，状态SEMANTICS_CONFIRMED / VALUE_QC_REQUIRED。

## 当前核心公式
### 市场规模
GrossUnits = SUM(DISTINCT SKU.soldCount)
NetUnitsEst = SUM(DISTINCT SKU.soldCount × redemption_rate)
GrossGMV = SUM(DISTINCT SKU.gmvSum)
NetGMVEst = SUM(DISTINCT SKU.soldCount × redemption_rate × avgPrice)
ASP_net_est = NetGMVEst / NetUnitsEst
每个SKU只在一个产品族内计一次；exact/close/broad分别计算。

### CR4
CR4_gross = 按gross销量重新排序的Top4 / 所有可匹配P6 SKU gross销量。
CR4_net_est = 按net_est销量重新排序的Top4 / 所有可匹配P6 SKU net_est销量。
两者都是P8前108位可观测样本口径。

### Entry
max_slot30 = position<=30中单一seller_id占据的不同SKU最大数量。
new_top10 = top10中上架不足60天SKU数 / top10有效create_date SKU数。
B=1-min(max_slot30/10,1)，N=min(new_top10/0.4,1)。
EntryScore=100×(0.6B+0.4N)。
注意原仓库代码尚未实现生产版，当前样例不代表全量生产计算。

### 新品预测
当前不能可靠给出30–90天预测。0.15/0.27/0.54只可作为先验情景系数；需连续历史快照和新品爬坡结果回测后才能校准。

### 利润
净利润模型需先用net_est收入，再扣真实佣金、支付费、物流、采购、国内运费、包装、广告实际消耗和失败订单相关成本。当前缺少类目费率、重量尺寸/最新运费和广告账单，故不输出伪精确ROI。

## 必须补充的数据（优先级）
P0：
1. 连续两期以上P6同口径快照（至少28天间隔/窗口元数据）及P7连续月度快照，用于增长验证。
2. 商品详情接口variants/variationIds/variationsRelationId、条码/型号、商品标题属性、主图，用于L2a exact/close归并。
3. Ozon按category3与FBO/FBS拆分的实际佣金/服务费率表。
4. 实际物流资费表及重量、长宽高；优先补齐候选SKU，特别是volume>0.6L。
5. 代表性SKU广告账单：实际花费、归因GMV、推广模式，校验DRR。

P1：
6. 取消、拒收、未取件、退货、妥投的订单状态构成及逆向物流费用。
7. P8其他卖家报价完整快照：offer SKU、seller_id、价格、时间，识别跟卖与同卡多卖家。
8. 前台stock_max每日快照及补货/仓间变化标记，用于校准库存消耗代理。

## 当前建议执行顺序
1. 重算gross/net_est产品簇和关键词市场规模、双口径CR4。
2. 建立L2a产品族；先用商品详情变体关系/条码/型号和其他卖家报价，标题图像仅做候选。
3. 全量实现max_slot30/new_top10并与人工抽样核验。
4. 建立利润成本表和情景模型；缺值显示区间/未知。
5. 开始定期保存P6/P7/P8快照，积累30/60/90天预测训练集。
6. RSI先运行数据质量与预测回测诊断，不自动更改生产模型。
