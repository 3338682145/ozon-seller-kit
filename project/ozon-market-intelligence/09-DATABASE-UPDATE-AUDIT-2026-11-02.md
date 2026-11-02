# Ozon Market Intelligence — 数据库更新审计（2026-11-02）

## 1. 文件与完整性
- 来源：Google Drive / ozon-data / toys.db
- Drive File ID：1HdWipkSd0f8aw6Zsb_n6-UhnyX_fD_yD
- 大小：128,512,000 bytes
- SHA256：33e5f02961c2782cead58e6714266aab6cbddc31e74242f905d2a7ba218502d8
- SQLite PRAGMA integrity_check：ok
- 只读分析，原始库未修改。

## 2. 新版数据库结构
新版 toys.db 有11张表：

| 表 | 行数 | 作用 |
|---|---:|---|
| blue_v3 | 142 | 蓝海分榜 |
| category | 1 | 类目绑定 |
| dim_cluster | 165 | 关键词簇 |
| fact_keyword_sku | 177,063 | 关键词-SKU-簇映射、ESI |
| keyword_p7 | 9,979 | P7搜索需求、动态、无行为、零结果、订单与GMV |
| keyword_score | 2,795 | SDR、Z分数、供需缺口、gate |
| keyword_seerfar | 1,642 | Seerfar关键词市场与供给 |
| keyword_sku | 177,063 | p8搜索位，含seller_id和商品标题 |
| product_seerfar | 100 | 商品标题、卖家、重量、尺寸、变体关系等原始JSON |
| query_metrics_v2 | 1,642 | 关键词综合指标 |
| sku_snapshot_v2 | 29,823 | p6 SKU销量、GMV、库存、DRR等 |

旧版 toys-slim.db 仍保留 sku_weekly(4,350)，但新版 toys.db 不含该表。两份数据库应独立留档；统计窗口确认后才可合并使用。

## 3. 关键数据完整性
- sku_snapshot_v2：29,823行；sku、name、brand、seller_id、category3、sold_count、gmv_sum、avg_price、drr、promo_revenue_share、stock、volume等核心列均非NULL。
- keyword_sku：177,063行；keyword、sku、position、price、seller_id、name均非NULL；CPC缺失94,803行（53.54%）。
- keyword_p7：9,979行；no_action_share、zr_share、count_28d完整；dyn_7d/dyn_28d各缺4行。
- keyword_seerfar：1,642行；growth_90d全空；return_cancel_rate、weight、volume、sales、revenue各缺9行。
- p8到p6按SKU连接：177,063条记录中143,917条能连接，行级覆盖81.28%；48,898个不同搜索位SKU中，29,823个能匹配p6。未连接不得视为零销量。
- query_metrics_v2 measured_at=2026-10-30；keyword_p7 snap_date=2026-10-29；fact_keyword_sku snapshot_date=2026-10-30。
- P7与1,642个Seerfar关键词按原始query精确匹配仅560个；1,082个未精确匹配。不能把未匹配解释为无需求，需词形标准化和人工审核映射。

## 4. DRR 数据风险登记（重要）
用户明确要求DRR可能存疑。从2026-11-02起，drr状态为 `SUSPECT / QUARANTINED`：
1. 不作为硬门槛，不据此淘汰商品。
2. 不代入正式净利润、ROI和COGS上限的单点结果。
3. 可以展示原始值，但必须附风险标记。利润先展示不含广告的基础值，并给DRR 0%、5%、10%、15%情景。
4. drr=0不能自动解释为自然流量或未投广告，需核验语义。
5. 不删除、不覆盖原始DRR，保留raw_drr、source、snapshot_date和异常标记。

### DRR实测分布
- drr=0：15,471/29,823（51.9%）。
- drr>0：14,352；正值中位数8.64，P75=16.77，P90=29.11，P95=41.12，P99=96.90。
- drr>30：1,327个；drr>100：137个；最大10,431.14。
- 抗压玩具类目16,039 SKU；drr>100有43个；drr>30有566个；drr=0有10,380个。
- 100个product_seerfar样本中，94个SKU能与p6连接并同时取得raw_json.drr；两来源DRR相关系数约0.9957，中位比值约1.013。样本有限，且不能代替平台定义核验，不能据此解除隔离。
- drr>100的137个SKU销量合计仅1,519件，低销量分母放大、口径或采集质量均需进一步检查。

解除隔离前必须：确认指标定义/分母、百分比单位和统计窗口；与真实广告花费及归因GMV抽样对账；解释异常值和0值语义；经人工批准验证报告。

## 5. 结单率口径
记录用户业务解释：redemption_rate为成功结算率，1-redemption_rate可作为未成功结算比例。正式模型仍需确认未结算是否全部为退货，还是含拒收、取消、未取件、配送失败。若混合，字段命名为non_settlement_rate，不直接称return_rate。keyword_seerfar.return_cancel_rate是另一个字段，不可混用。

## 6. P7需求质量
- no_action_share>40：1,769词。
- 25–40：5,472词。
- <=25：2,776词。
- P7全库均值32.71%，中位数29.8%。
- P7精确匹配Seerfar的560词中，平均no_action_share约29.73%，其中58词>40。
- P7搜索量与Seerfar搜索量不能简单相加；精确匹配仅560词。

## 7. 市场样本基线
category3='抗压玩具'：16,039 SKU，p6窗口销量1,117,485件，GMV 248,221,059.332 RUB，加权成交价222.12 RUB，seller_name去重5,693。仅代表数据库可观测SKU样本，不宣称全Ozon完整市场规模。

## 8. 可打入性复算
新版keyword_sku已有seller_id。max_slot30必须按真实seller_id聚合不同SKU，不再用seller_name代理。快照基准2026-10-30：

| 关键词 | max_slot30 | new_top10 | EntryScore |
|---|---:|---:|---:|
| сквиши набор популярные | 3 | 30% | 72 |
| антистресс пистолет | 2 | 20% | 68 |
| сквиши сыр | 2 | 20% | 68 |
| поп ит большой | 4 | 30% | 66 |
| антистресс нидл | 4 | 30% | 66 |
| нидл антистресс | 4 | 20% | 56 |
| сквиш нидл | 4 | 20% | 56 |
| магнитные шарики антистресс | 4 | 10% | 46 |
| ручка спиннер | 4 | 10% | 46 |
| мальтозный шар | 7 | 20% | 38 |

公式：B=1-min(max_slot30/10,1)；N=min(new_top10/0.4,1)；EntryScore=100×(0.6B+0.4N)。p25_top10另作价格压力指标。

## 9. 下一步
1. 接入Drive bestsellers_latest.parquet（1,962,354行，2026-10-21快照）补齐variantId、商品身份、卖家ID、图片、重量和尺寸；其快照早于p6，需防止跨期混合。
2. 接入keyword_month / keyword_window，核实与SQLite P7的字段及时间窗口关系。
3. 建立产品族exact/close/broad映射，保存证据、置信度和人工复核状态。
4. DRR继续隔离；核实字段定义、百分比单位、低销量异常和广告花费金额关系。
5. 结单率、真实佣金、最新物流费率、重量/尺寸确认后再发布正式利润/ROI排名。
6. 每次数据库、Parquet、规则配置和计算报告生成snapshot_id与SHA256；原始数据本地留存，GitHub同步文档/代码/轻量manifest，不提交大数据库或Cookie。
