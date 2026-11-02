# 08 — SQLite 数据库初审报告（2026-11-02）

## 1. 文件与完整性
- Drive 文件：ozon-data/toys-slim.db
- Drive File ID：1ou9mlrc01SO_qLzGQoLvUOWQGofUPJGe
- 文件大小：19,861,504 bytes
- 本次下载文件 SHA256：3de3d7260049bf420cf944c2ba64cb18a91acff5390ef167a23506ad51304f68
- SQLite PRAGMA integrity_check：ok
- 以只读模式打开；未改写原始数据库。

## 2. 实际表与行数
| 表 | 行数 | 用途 |
|---|---:|---|
| kw_metrics | 1,642 | 关键词指标 |
| kw_positions | 177,063 | 关键词搜索位 |
| sku | 29,823 | SKU p6快照 |
| clusters | 165 | 关键词簇 |
| sku_weekly | 4,350 | SKU月/周销量动态与加速度 |

与seller-kit README的四张核心表行数吻合；实际还发现第五张表sku_weekly，是重要增量数据。

## 3. 数据时间与覆盖
- kw_metrics.measured_at唯一值：2026-10-30。
- kw_positions：1,642个关键词；1,636个关键词恰好108条记录，5个少于108条，1个多于108条；全表position范围1–465，只有3条记录position>108。
- kw_positions有48,898个不同SKU；其中143,917/177,063条记录能关联到sku表，行级join率81.28%；未关联33,146条。不能把未关联解释为零销量，必须保留join_missing状态。
- sku表29,823个SKU均有唯一sku键，未发现重复主键。
- p6 avg_price与gmv_sum/sold_count在全部SKU上差异均小于0.01，内部一致性很好。
- sku_weekly有4,350个唯一SKU，全部能关联sku表；其monthly_sold与p6 sold_count相关系数0.99964，平均绝对差11.95，表明两列高度接近但仍应保留原字段，不要覆盖。
- sku_weekly.accel与weekly_sold*4/monthly_sold最大差异约0.0005，公式基本确认。

## 4. 关键词层质量与竞争分布
- Coverage中位数88.89%，均值81.24%；Coverage>=70%的1,277词，<40%的105词。
- CR4中位数45.61%；CR4>50%的656词，<=30%的261词；有1条CR4为空。
- Homogeneity中位数100%；>=90%的1,033词，<70%的406词，19词为空。
- kw_positions的rating/reviews缺失率19.48%；CPC缺失率53.54%。CPC不宜做全量硬门槛。
- kw_positions本身没有seller_id字段；本次max_slot30用sku表seller_name回连作为代理，正式版应优先接入bestsellers_latest.parquet里的sellerId。

## 5. SKU层异常与清洗
- sku.sold_count：29,823行均有值，最小1，中位数9，最大52,362。
- drr=0有15,471个（51.9%），应解释为未投放；drr>100有137个，最大10,431.14，需标记异常，不得直接进入利润计算。
- sales_dynamics缺失7,516个（25.2%）；>1,000的770个，最大247,961，打分前必须截尾/稳健变换，且保留原值。
- volume中位数0.6L；>100L有19个，最大6,480L，需做单位/异常核验。
- redemption_rate缺失126个，等于0的661个；中位数93.7%，P25=85%。0值SKU的销量中位数仅1件，建议低样本时将结单率标为低置信度，不要机械地把100%未结单损耗应用于所有SKU。
- stock、accessibility_by_days是单时点字段，不可据此推导长期库存周转趋势。

## 6. 解压玩具大类的可观测市场样本
筛选sku.category3='抗压玩具'：
- SKU数：16,039
- p6快照窗口销量合计：1,117,485件
- GMV合计：248,221,059.33 RUB
- 加权成交均价：222.12 RUB
- 不同seller_name：5,693
- SKU销量中位数：5件
- 体积中位数：0.448L；volume>=0.6L占40.24%
- DRR=0占64.72%；非零DRR中位数8.31
- promo_revenue_share>50%的SKU占48.06%
- redemption_rate中位数99.0%，0值452个
- sales_dynamics中位数5.35%，缺失4,721个

以上是当前p6 SKU样本中的“抗压玩具”三级类目观测规模，不等于Ozon全站完整类目规模；不可与关键词搜索量相加。

## 7. sku_weekly带来的趋势能力
- 全表4,350个SKU中，accel>1有2,070个，>1.5有814个，<0.7有1,232个。
- 抗压玩具类别中覆盖2,333个SKU：accel>1有1,044个，>1.5有386个，<0.7有777个。
- accel = weekly_sold*4/monthly_sold，可作为近期周销运行速度相对月度基线的动量信号；它不是未来销量预测本身。
- weekly_dyn与monthly_dyn应分开保存；不要将周环比与月动态直接求平均。
- sku_weekly表没有独立snapshot_date/period_start/period_end字段，必须从数据生成记录或manifest补齐统计窗口，才能作为正式时序训练数据。

## 8. 可打入性复算样例
计算基准日采用kw_metrics.measured_at=2026-10-30。
- max_slot30：position<=30中按不同SKU统计seller_name的最大占位数。因kw_positions缺seller_id，本次用sku.seller_name做代理，需在正式模型中由sellerId复核。
- new_top10：top10中create_date有效且上架不足60天的SKU数 / top10有效日期SKU数。
- p25_top10：沿用SOP定义，top10挂牌价从低到高第3个价格。
- EntryScore = 100 × [0.60×(1-min(max_slot30/10,1)) + 0.40×min(new_top10/40%,1)]。

| 关键词 | 搜索量 | 增长30d | Coverage | CR4 | max_slot30 | new_top10 | p25_top10 | EntryScore |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| сквиши набор популярные | 1,026 | +41.91% | 100.00% | 36.70% | 3 | 30% | 201 | 72 |
| антистресс пистолет | 2,393 | +7.17% | 97.22% | 32.94% | 2 | 20% | 234 | 68 |
| сквиши сыр | 2,283 | +10.08% | 98.15% | 25.77% | 2 | 20% | 188 | 68 |
| поп ит большой | 1,454 | +3.78% | 92.59% | 32.06% | 4 | 30% | 228 | 66 |
| антистресс нидл | 1,145 | +288.14% | 99.07% | 27.96% | 4 | 30% | 239 | 66 |
| нидл антистресс | 2,261 | +238.47% | 99.07% | 28.49% | 4 | 20% | 237 | 56 |
| сквиш нидл | 6,323 | +22.78% | 100.00% | 26.90% | 4 | 20% | 201 | 56 |
| магнитные шарики антистресс | 1,494 | +9.21% | 94.44% | 33.54% | 4 | 10% | 331 | 46 |
| ручка спиннер | 1,104 | +6.87% | 87.96% | 44.81% | 4 | 10% | 200 | 46 |

这些是关键词层可打入性，不等于最终产品族得分。相同需求的近义词需先归并再给产品族决策，不能重复占用机会名额。

## 9. 假蓝海复核：мальтозный шар
- 搜索量10,990；growth_30d +146.86%；Coverage 80.56%；CR4 43.98%。
- max_slot30=7（seller_name代理口径）；BrotherShop在top30占7个不同SKU。
- top10有效上架日期10个，其中60天内新品2个；new_top10=20%。
- top10第3低价=241 RUB。
- EntryScore=38/100。
- 结论：高搜索增长不能抵消货架壁垒；与项目原则“可打入性优先于吸引力”一致。卖家ID应从补充bestsellers快照复核。

## 10. 当前不能仅凭SQLite完成的事项
1. SQLite的sku表没有商品标题、图片、variantId、sellerId；kw_positions也没有seller_id。因此无法只凭该DB高精度建立exact同款产品族，也无法准确识别同卖家多店铺/名称别名。
2. SQLite没有P7 no_action_share / zero_result_share表。Drive目录另有keyword_month.parquet、keyword_window.parquet、keyword_category.parquet，可作为P7/搜索需求补充源。
3. Drive manifest显示bestsellers_latest.parquet有1,962,354行，包含sku、variantId、name、skuName、sellerId、category3、volume、position、snapshot_date等字段；这是建立产品族、sellerId和商品标题映射的关键补充数据。需解析并与SQLite SKU连接。
4. dim_categories.parquet包含9,144行类目维表。
5. 当前SQLite单期p6快照不能计算产品族真实历史销量增长。sku_weekly可提供近期动量，但缺少自身统计窗口元数据；正式预测需建立连续快照。

## 11. 下一步
P0已完成SQLite完整性和结构初审。下一步先接入bestsellers_latest与keyword_month/window数据，补齐产品身份、sellerId和P7需求质量；再建立exact/close/broad产品族映射，进行SKU去重后的产品市场规模计算。利润核算前仍需核验redemption_rate、佣金、重量/尺寸和最新物流费率。
