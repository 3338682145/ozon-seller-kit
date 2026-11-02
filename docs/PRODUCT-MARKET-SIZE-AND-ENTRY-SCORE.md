# Ozon 产品级市场规模与可打入性选品模型

版本：v1.0
适用数据：ozon-seller-kit 的 toys-slim.db 及后续同结构快照
核心原则：**可打入性优先于市场吸引力**。先判断货架能否进入，再估算市场规模，最后计算单位经济与 ROI。

## 0. 数据口径与边界

主表映射（以实际 SQLite schema 为准）：

- query_metrics_v2：关键词搜索量、增长、覆盖率、CR4、同质度、价格、竞争商品数、DRR 等。
- keyword_sku：关键词 × SKU × 搜索位（p8），含 position、price、seller_id、promo、cpc。
- sku_snapshot_v2：SKU 级 p6 快照，含 sold_count、gmv_sum、avg_price、volume、drr、stock、rating、reviews、create_date、redemption_rate、promo_revenue_share。
- dim_cluster / fact_keyword_sku：关键词簇和关键词归属。
- keyword_p7：P7 28 天搜索量、7/28 天变化、零结果率、无行为率、订单、GMV 等。
- sku_power：启发式曝光能力，粒度为 (sku, cluster)，必须先按 sku 聚合，不能直接取单行。

必须保留字段来源标签：平台采集真值、第三方估算、派生指标、人工假设。p8 只有前 108 个搜索位；基于它算出的 CR4、SKU 份额和市场规模均为“可观测搜索位样本”，不能称为全站完整市场真值。p6 是单期快照，不等于历史趋势序列。只有至少两个不同日期的快照，才可计算 SKU 级真实环比。

## 1. 产品族归并：先把同款 SKU 找全

建立 product_family_map(product_family_id, sku, match_type, confidence, evidence)，每个 SKU 只归属一个主产品族；无法确定的 SKU 保留为待人工审核，不强行合并。

归并证据优先级：

1. 相同 Ozon 商品卡/变体族 ID（若数据源可取）；
2. 标题去品牌、规格、颜色、套装数量后的核心词相似度；
3. category3/category3_id、材质、形态、尺寸、件数等属性一致；
4. 主图/详情图视觉相似度；
5. 人工复核边界案例。

输出三种口径：
- exact：确定同款/同一变体族；
- close：相似形态、可互相替代的竞品；
- broad：同一需求下的所有产品。

不得把 exact、close、broad 混成一个市场规模。报告分别给出精确同款市场、可替代品市场、广义需求市场。跨关键词重复出现的 SKU 必须 DISTINCT 去重；跨变体卡片疑似合并时需标注。

## 2. Machine Gate：先排除假需求和结构性红海

建议阈值（可配置，不应把所有阈值写死在代码中）：

| 指标 | 主推池 | 观察池 | 淘汰/警告 |
|---|---:|---:|---:|
| Coverage | >=70% | 50–70% | <50% 不做确定性利润决策 |
| CR4（按销量，不按排名） | <=30% | 30–45% | >50% 红海警示 |
| Homogeneity | >=90% | 70–90% | <70% 需求意图分散 |
| P7 no_action_share | <=25% | 25–40% | >40% 假需求/泛词警示 |
| Growth | >0 | -10–0% | <-10% 衰退警示 |
| 样本量 | n_p6 >=30 | 15–29 | <15 统计不稳定 |
| IP | 无高风险商标/版权 | 待核验 | 确认侵权直接否决 |

Coverage 必须同时报告 n_items、n_p6 和 join 失败原因。覆盖低可能是数据未匹配，不能直接推断市场没有销量。CR4 的分母为该关键词 p8 108 位中成功关联 p6 的 SKU 销量总和，公式：

CR4 = SUM(销量最高的4个不同SKU) / SUM(该词可匹配SKU销量)

另报 CR4_n、分母销量和可匹配 SKU 数。不能用 position 前四名，也不能用 popularity 代替销量。

## 3. 可打入性 Entry Score：最高权重

按关键词计算：

- max_slot30：position<=30 中，单一 seller_id 占据的最大 SKU 位数。按不同 SKU 去重后计数。
- new_top10：top10 中上架不足 60 天且有 create_date 的 SKU 数 / top10 中有有效 create_date 的 SKU 数。
- p25_top10：top10 有效挂牌价的 25 分位数（同时输出样本量与中位数）。

标准化：
- B = 1 - MIN(max_slot30 / 10, 1)，单卖家占满 10 位时为 0；
- N = MIN(new_top10 / 0.40, 1)，前排新人率达到 40% 时封顶；
- P = MIN(MAX((p25_top10 - 150) / 100, 0), 1)，仅作价格空间辅助项。

EntryScore = 100 * (0.60*B + 0.40*N)

可打入性判读：
- >=70：货架结构友好；
- 50–70：可测款，检查竞价和价格带；
- 30–50：进入成本偏高；
- <30：货架壁垒高，原则上不主推。

全局机会评分（0–100）：
OpportunityScore = 0.50*EntryScore + 0.15*DemandScore + 0.10*GrowthScore + 0.15*ProfitScore + 0.05*CoverageScore + 0.05*P7QualityScore

这里 EntryScore 权重 50%，且 max_slot30 / new_top10 是 EntryScore 内的全部权重。市场大但进不去，不能被高搜索量补偿。IP 命中、明确侵权、P7 无行为率 >40%、CR4>50% 且无供应链优势等可作为硬否决，不参与加权。

DemandScore = 100 * MIN(LN(1 + P7_count_28d) / LN(1 + 30000), 1)
GrowthScore = 100 * CLAMP((weighted_growth_28d + 20) / 120, 0, 1)
CoverageScore = 100 * CLAMP(coverage / 100, 0, 1)
P7QualityScore = 100 * (1 - CLAMP(no_action_share / 100, 0, 1))

增长必须同时展示 P7 dyn_7d、dyn_28d 与 Seerfar growth_30d；Seerfar 极端增长值在评分时截断至 100%，不得用算术平均放大离群值。

## 4. 产品市场规模：同款 SKU 归并后计算

对每个产品族分别计算 exact / close / broad 三种市场范围。SKU 先去重，再与 p6 快照关联。

产品族月销量：
MarketUnits28d = SUM(DISTINCT SKU 的 sold_count)

产品族月 GMV：
MarketGMV28d = SUM(DISTINCT SKU 的 gmv_sum)

加权成交均价：
MarketASP = MarketGMV28d / MarketUnits28d

市场销量份额：
SKUShare = SKU.sold_count / MarketUnits28d

市场销售额份额：
GMVShare = SKU.gmv_sum / MarketGMV28d

卖家数：
SellerCount = COUNT(DISTINCT seller_id)

头部集中度：
FamilyCR4 = 产品族内按 sold_count 排序的前4个 SKU 销量 / MarketUnits28d

重要：同一 SKU 命中多个关键词只能计一次。若同一商品卡的多件装/变体被合并，必须分开统计 SKU，再另行输出“父商品族”口径，不能把不同件数的价格与销量当成同款单件。

市场增速：
- 若有同 SKU 两期 p6 快照：SKU 级增长 = (本期 sold_count - 上期 sold_count) / 上期 sold_count；产品族增长按上期销量加权。
- 若没有历史 p6：只能报告 P7 dyn_7d / dyn_28d 和 Seerfar growth_30d，标签为需求搜索增速，不得写成产品销量增速。
- 当前仓库单快照不能独立算出真实产品销量环比。

## 5. 新品预期：保守 / 基准 / 乐观

对标样本限定在候选关键词 top10、且产品形态相符的 SKU。先去重 SKU，再计算中位月销。

BaseComparableSales = MEDIAN(合格对标 SKU 的 sold_count)

预期新品月销量：
- 保守：BaseComparableSales * 0.15
- 基准：BaseComparableSales * 0.27
- 乐观：BaseComparableSales * 0.54

0.54 是仓库 SOP 的横截面追赶系数上限，不是保证值；0.27 作为基准经营假设。再加市场份额上限：
ForecastUnits = MIN(情景销量, MarketUnits28d * 情景份额上限)
建议初始份额上限：保守 0.5%、基准 1%、乐观 2%，上线后用自店真实数据校准。

ForecastGMV = ForecastUnits * MarketASP
ForecastGrossProfit = ForecastUnits * UnitProfit
必须同时输出对标 SKU 数量、销量中位数、P25/P75；样本少于 3 个时，预期标低置信度，不应只给一个确定数。

## 6. 利润、采购上限与 ROI

统一币种：售价、平台费用、广告、俄罗斯物流以 RUB 计；采购、国内头程以 CNY 计；汇率 E = RUB/CNY，按当期真实结算汇率输入。利润引擎不能把两种币种直接相减。

输入：
- P：Ozon 买家实付均价 RUB，优先用 p6 avg_price = gmv_sum/sold_count；
- c：真实类目佣金率；
- f：平台支付/服务费率；
- d：DRR 广告费率；drr=0 表示无广告，不是缺失；
- L：跨境运费 RUB/件，优先用 selection-helper-local 的渠道/重量/体积重资费表；
- C：1688 采购成本 CNY/件；
- H：国内运费及包装 CNY/件；
- E：实际 RUB/CNY 汇率；
- label：贴标/操作等 RUB/件。

单位净贡献（RUB）：
UnitProfit = P*(1-c-f-d) - L - label - E*(C+H)

单位利润率：
UnitMargin = UnitProfit / P

投入成本（CNY）：
UnitInvestment = C + H + (L+label)/E + (P*(c+f+d))/E

ROI：
ROI = UnitProfit/E / (C+H+(L+label)/E)

ROI 与利润率不是同一指标，报告必须两者都给。

目标净利率 m 下的最高采购价：
COGSmax_CNY = [P*(1-c-f-d-m) - L - label] / E - H

若 COGSmax<=0，直接判定当前售价/费用结构无法达到目标利润率。佣金不能默认照搬 23%；优先使用商品实际类目费率。selection-helper-local 的 13/15/17 档是代码估算值，AUDIT 已提示并非真实类目费率。其运费表可按渠道、实重、体积重、申报价、服务档计算；运费日期为 2026-04-15，使用前要核验最新报价。

退货/结单率：redemption_rate 是结单率，不是退货率。没有独立退货率时，基础利润与退货压力情景分开报告，不能把 1-redemption_rate 直接当退货率。

## 7. 结果交付字段

每个产品族输出：

- 产品族 ID、中文/俄文名称、exact/close/broad 口径、归并置信度；
- SKU 总数、SKU ID 全清单、去重卖家数、p8 可见 SKU 数；
- MarketUnits28d、MarketGMV28d、MarketASP、FamilyCR4、Top1/Top4 份额；
- P7 28d 搜索量、7d/28d 搜索变化、无行为率、零结果率；
- p6 销量增长（仅当有历史快照时）、搜索需求增长与销量增长分开显示；
- max_slot30、new_top10、p25_top10、EntryScore、OpportunityScore；
- 对标 SKU 清单及销量/价格/体积/DRR/促销占比；
- UnitProfit、UnitMargin、ROI、COGSmax；
- 保守/基准/乐观月销量、月 GMV、月利润；
- 数据覆盖率、样本量、字段来源、IP 风险、异常警告。

## 8. 当前仓库可计算性说明

seller-kit 的 README 和 SOP 公开了字段、表关系、样本量与若干已跑出的候选汇总；但 toys-slim.db 是二进制 SQLite 文件，当前 GitHub 连接器只能读取 UTF-8 文本，不能把该二进制数据库载入分析运行时。因此不能仅凭 README/SOP 还原全部 SKU ID 清单或重新执行全库聚合。

现有 SOP 中可复用的已计算样例（2026-10-30 快照）：
- сквиш нидл：6 个合格对标 SKU，中位月销 3,056，体积 0.22L，中位价 229₽，中位净利 68₽/件，采购上限 8.8 元；
- сквиши сыр：3 个对标 SKU，中位月销 621，中位价 248₽，采购上限 9.8 元；
- антистресс пистолет：1 个对标 SKU，中位月销 469，中位价 231₽，采购上限 8.7 元；
- магнитные шарики антистресс：2 个对标 SKU，中位月销 368，中位价 509₽，采购上限 25.0 元；
- поп ит большой：1 个对标 SKU，中位月销 340，中位价 237₽，采购上限 8.9 元。

这些是 SOP 已公布的对标摘要，不是本文件重新读取 SQLite 后复算的结果。完整产品级市场规模和 SKU ID 清单必须在拿到数据库或 CSV 导出后计算。
