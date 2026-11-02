# 12 — 字段字典核验与模型口径修订（2026-11-02）

## 1. 来源与证据等级
- 来源：用户提供的 Ego-Browser DOM 悬停字段解释实录；声明已同步至 ozon-seller-kit，提交短 SHA c8e5a5a。
- GitHub实际核验到完整提交：9f28beab52f095761242307673e4d64168c16922；同次提交包含 docs/DATA-VERIFICATION-12-ITEMS.md。
- A级：Ozon UI原生悬停解释；B级：原始接口字段/实测；C级：工程备注或推断。C级不得写成官方定义。

## 2. P6字段正式口径
| 字段 | 核验含义 | 模型处理 |
|---|---|---|
| soldCount | 28天订购商品数量，包含取消和退货 | 毛下单件数，不是最终妥投净销量 |
| gmvSum / soldSum | 订购商品总价值，含取消和退货，按销售价格计算 | 毛订单GMV，不是最终净收入 |
| avgPrice | 期间平均销售价格；实测约等于gmvSum/soldCount | 毛订单平均价，与前台挂牌价分开 |
| nullableRedemptionRate | 未取消且未退回的订购商品百分比 | 成功结单/妥投留存率；不是退货率 |
| salesDynamics | 与上一期相比订单总金额的变化 | GMV动态，不是件数增长 |
| daysInStock | 最近28天有库存的天数；-1表示停售或无数据（字段方向需复核） | 可售天数；UI中文表头和悬停解释有措辞差异，需二次确认 |
| avgGmvOnAccDays | FBO/FBS订单金额÷有库存天数，含取消/退货 | 有货日毛GMV速度 |
| avgOrdersOnAccDays | FBO/FBS订单数÷有库存天数，含取消/退货 | 有货日毛下单速度 |
| sumMissedGmv | 有库存时本可赚取金额，基于日均销量 | 缺货机会损失，不加进实际GMV |
| stock/fboStock/fbsStock | 统计周期最后一天库存 | 后台申报库存，不等于买家端真实物理库存 |
| salesSchema | Ozon仓或卖家仓及配送合作模式 | FBO/FBS分层 |
| volume | 包装商品体积，单位L | 物流/仓储体积；P6无重量及长宽高 |
| drr | 推广费用与订购商品价值之比；统计所有订单含取消/退货，按价格上限计算 | 定义有官方UI解释；极端值仍须质量控制 |
| daysWithTrafarets | 搜索/推荐CPC推广天数 | 28天内推广活跃天数，可辅助核验drr=0 |
| daysInPromo | 期间参与促销天数 | 0–28天促销强度 |
| promoRevenueShare | Ozon促销订单金额占全部订单金额比例 | 毛订单促销依赖度 |
| views | 网站所有页面展示次数 | 全站曝光 |
| sessionCountSearch | 搜索与目录展示次数 | 搜索曝光，与views分开 |
| qtyViewPdp | 进入商品卡次数 | PDP访问 |
| convViewToOrder | 各页面订单量/展示量比值 | 展示至下单转化 |
| convToCartSearch | 搜索结果展示后加购率 | 搜索列表吸引力 |
| convToCartPdp | 商品卡浏览后加购率 | 详情页加购表现 |
| meanPriceDiscount | 按促销订单中位价、最高价格计算的平均折扣 | 促销/排名特征，不替代实际成交价 |
| minSellerPrice | UI解释为买家购买最低销售价格 | 工程实测约49.2%样本偏低，可能受变体最低价影响；不可当单SKU门槛 |

P6同一次请求中的SKU共享28天窗口；响应没有明确period_from/period_to，p6采集日2026-10-30与P7快照日2026-10-29不能假设完全对齐。

## 3. P7字段正式口径
| 字段 | 核验含义 | 模型处理 |
|---|---|---|
| count_28d | 过去28天搜索过商品的独立买家数 | 搜索需求人数，不是搜索事件次数 |
| dyn_7d/dyn_28d | Ozon提供7天/28天需求动态 | 精确比较基准未知；不能擅自称标准环比/同比 |
| ca | 从该搜索结果进入并至少加购一件的买家数 | 搜索引导加购人数 |
| conv_to_cart | 搜索结果进入后加购买家百分比 | 搜索需求质量 |
| ord | 通过搜索结果下单的独立买家数 | 买家人数，不是商品件数 |
| conv_pct | 搜索结果进入并订购商品的买家百分比 | 搜索转化率 |
| gmv | 搜索结果带来的订购商品总价值，含取消/退货，并考虑自提点处理费 | 毛订单GMV；不可与P6直接相加 |
| avg_price | 平均销售价，含自提点订单处理成本 | P7价格口径，独立保存 |
| items_views | 买家按该搜索查询浏览商品的平均数量 | 浏览深度，不是SKU总量 |
| no_action_share | 搜索后未点击任何商品结果的查询占比 | 需求意图/结果页吸引力风险，不等于假需求 |
| zr_share | 未找到合适商品的搜索查询占比 | 潜在供给缺口，需结合需求量和订单验证 |
| group_name | 一级类目分组 | 必须严格匹配官方标准分组，否则可能静默返回0条 |

P7 count_28d为28天窗口，快照日2026-10-29。P7 dyn与Seerfar growth_30d相关但不等值；DATA-VERIFICATION-12-ITEMS确认当前无法确定其精确统计基准，需连续月份快照验证。

## 4. P8字段正式口径
- generalPopularity：由打开、订购、加购、收藏、对比等行为形成的综合热门度，绝非销量；禁止用于CR4。
- promotionCpcRate：CPC推广出价，不是实际扣费。
- promotionCpoRate：按订单付费推广比例/出价。
- textRelevance：名称、描述及其他字段与查询的匹配度，可作为Listing SEO特征。
- reviews：评价信号。
- price：买家在网站商品卡/App看到的价格，即前台挂牌价，与P6成交均价分开。
- salePromotions：Ozon促销状态/搜索提权信号。
- deliveryPeriod：搜索结果展示配送时效。
- relevance：当前177,063行实测100% NULL，作为死字段弃用。

## 5. 核心计算方法修订
设U_gross=soldCount，r=nullableRedemptionRate/100，P=avgPrice=gmvSum/soldCount。

估算妥投净件数：`U_net_est = U_gross × r`。
估算妥投净GMV：`GMV_net_est = U_net_est × P`。

净GMV是按毛订单均价推算的估计值，不是平台直接提供的最终结算金额；若未结单订单与妥投订单价格结构不同，会产生偏差。所有报告同时展示gross和net_est。

### CR4双口径
- `CR4_gross = gross销量Top4之和 / 全部可匹配SKU gross销量`。
- `CR4_net_est = net_est销量Top4之和 / 全部可匹配SKU net_est销量`。
- 两种口径各自重新排序Top4。分母仅是当前关键词P8可观测且成功关联P6的SKU，不是全站完整市场。

### 产品族市场规模
先按product_family_id映射SKU并DISTINCT去重，再计算gross_units、net_units_est、gross_gmv、net_gmv_est、ASP、卖家数、Top1/Top4份额。一个SKU跨多个需求簇时可分别参与簇分析，但跨簇总市场必须全局去重。Exact/close/broad分别输出。

### 库存校正
`avgOrdersOnAccDays × 28`可作为假设全28天有货时的毛订单需求运行率估计；`avgGmvOnAccDays × 28`为对应毛GMV运行率。它们仍包含取消/退货，不替代实际soldCount。`sumMissedGmv`单独列为缺货机会损失，不加入实际市场规模。

### 搜索需求
P7 count_28d作为独立搜索买家规模；ca、ord作为独立买家加购/下单人数；conv_to_cart、conv_pct作为转化质量；no_action_share衡量无点击流失；zr_share衡量无合适商品的供给缺口。跨关键词累加人数可能重复计入同一买家，只能标注“查询层活动量”，不能称去重消费者总数。

### 增速
- P6 salesDynamics只作为GMV动态指标。
- P7 dyn_7d/dyn_28d在拿到连续快照前标记为平台动态指数（比较基准未确认）。
- 产品真实销量增长需同口径连续P6快照计算：`(本期U_net_est-上期U_net_est)/上期U_net_est`。
- 旧版sku_weekly可提供动量特征，但必须确认统计窗口和来源日期后才能用于训练。

## 6. DRR政策修订
DRR定义已由P6 UI悬停说明确认：推广费用/订购商品价值，分母包括取消和退货，计算采用价格上限。原先“定义不明”状态应修订为：`SEMANTICS_CONFIRMED / VALUE_QC_REQUIRED`。
- drr=0按字段含义可作为0广告费份额；用daysWithTrafarets辅助交叉验证。
- 极端值（如>100%甚至数千%）继续标记异常，可能受GMV极小分母放大。
- 批量市场分析可展示DRR分布/中位数及异常比例；不得用极端值直接做硬淘汰。
- 单SKU利润优先核查P8 promotionCpcRate、promotionCpoRate、推广状态；CPC是出价不是实际花费。
- 真实广告费仍需账单或广告后台对账。保留raw_drr，不覆盖原值。

## 7. 当前实现状态与缺口
- 已有：L1 165个需求簇、L2簇-SKU聚合、L3 SKU实体、keyword-SKU与cluster-SKU桥表。
- 尚缺：L2a exact/close产品族归并；当前p6 sku与variantId在4,386样本中1:1，不能从该字段直接还原变体族。
- 需要：Seerfar product/detail的variants关系、variationIds/variationsRelationId、商品条码/型号、标题属性及图片证据；100条product_seerfar详情样本不足以覆盖全库。
- max_slot30/new_top10：字段齐备，但DATA-VERIFICATION-12-ITEMS标明原仓库计算代码尚未实现；当前少量样例计算不等于生产流水线已上线。
- 物流：P6只有volume；重量/长宽高需Seerfar detail按SKU补采。体积>0.6L运费模型当前风险高。
- 佣金：23%为人工假设，不能跨类目使用；需后台类目费率导出/合同依据。
- 库存：stock/fboStock/fbsStock为后台申报快照；前台stock_max可作为库存变化代理，但库存补货、购买上限2000、仓间调拨等会干扰，不能未经校准直接当真实销量。

## 8. 下一步核验优先级
1. 建立gross/net_est双口径市场规模与CR4，抽样手算核对。
2. 用product/detail variants与其他卖家报价建立L2a产品族，并对exact匹配抽样人工验收。
3. 实现max_slot30和new_top10的可复算SQL/Python流水线。
4. 接入连续P6/P7快照，确认动态字段语义并建立30/60/90天回测。
5. 获取类目佣金、物流最新费率、商品重量尺寸、广告账单及退货原因构成。