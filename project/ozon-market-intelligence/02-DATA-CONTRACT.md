# 02 — 数据字典与数据契约（2026-11-02核验版）

## 数据源与关键口径
| 来源 | 粒度 | 主要字段 | 已核验口径/限制 |
|---|---|---|---|
| P6 what_to_sell/data/v3 | SKU×28天快照 | soldCount, gmvSum, avgPrice, nullableRedemptionRate, salesDynamics, drr, volume, stock, daysInStock, avgOrdersOnAccDays | soldCount/GMV含取消退货；redemptionRate是未取消未退回占比；salesDynamics是金额动态；drr为推广费/订购金额 |
| P7 searchteam | query×28天快照 | count_28d, dyn_7d, dyn_28d, ca, ord, conv_pct, gmv, no_action_share, zr_share | count_28d是独立搜索买家数；ord/ca是独立买家数；gmv含取消退货和自提点处理费；dyn比较基准待核 |
| P8 explainer | keyword×position×SKU | position, price, seller_id, generalPopularity, promotionCpcRate, promotionCpoRate, textRelevance, reviews, deliveryPeriod | generalPopularity不是销量；CPC是出价非实扣；price是前台挂牌价；relevance全空弃用 |
| Seerfar | keyword/product×快照 | search_volume, growth_30d, conv_pct, competing_products, sellers, product detail | 第三方估算；增长与P7动态相关但不等值；商品详情变体/重量尺寸覆盖有限 |
| 1688/供应链 | SKU/报价×时间 | purchase_price, MOQ, domestic_shipping, weight, dimensions | 报价有有效期，规格需对应 |
| 物流费率 | 渠道×计费档 | base, per_gram, volumetric_divisor, service tier | 必须按有效日期版本化 |

## 核心事实表
### fact_sku_snapshot
sku TEXT、snapshot_date、period_days、sold_count_gross、gmv_gross_rub、avg_price_rub、redemption_rate_pct、sold_count_net_est、gmv_net_est_rub、sales_dynamics_gmv_pct、drr_raw_pct、drr_quality_flag、promo_revenue_share_pct、days_with_trafarets、days_in_promo、volume_l、stock_end、days_in_stock、avg_orders_on_acc_days、avg_gmv_on_acc_days、sum_missed_gmv、accessibility_by_days、create_date、seller_id、seller_name、sales_schema、category3_id、source、collected_at、raw_payload_ref。

### fact_keyword_position
keyword、snapshot_date、position、sku、seller_id、listed_price_rub、general_popularity、promotion_cpc_rate、promotion_cpo_rate、text_relevance、reviews、delivery_period、is_promoted、join_status、missing_reason。

### fact_keyword_demand
query、snapshot_date、period_days、count_28d_unique_buyers、dyn_7d_raw、dyn_28d_raw、ca_unique_buyers、ord_unique_buyers、conv_to_cart_pct、conv_pct、gmv_gross_rub、avg_price_rub、items_views_avg、no_action_share_pct、zr_share_pct、group_name、source、quality_flag。

### 产品族映射
dim_product_family：family_id、canonical_name_cn/ru、category3_id、family_scope、match_confidence、match_method、reviewed_by、ip_risk_status。
bridge_family_sku：family_id、sku、relation_type（exact/variant/close/substitute）、confidence、evidence_json、valid_from、valid_to。
bridge_family_keyword：family_id、keyword、relevance_score、intent_type、reviewed_flag。
bridge_cluster_sku与bridge_sku_keyword继续保留需求簇和关键词映射，不等同于产品族映射。

### 成本与预测表
fact_cost_quote：entity_id、quote_date、valid_until、supplier_url、purchase_cost_cny、MOQ、domestic_shipping_cny、packaging_cny、weight/dimensions、quote_confidence。
dim_logistics_rate：channel、service_level、tier、base_fee、rate_per_g、volumetric_divisor、weight/value cap、effective dates、source。
fact_forecast：entity_id、origin_date、horizon_days、model_version、scenario、forecast_units/gmv/profit、lower/upper bound、input_snapshot_ids。
fact_actual_outcome：entity_id、target_date、horizon_days、actual_units/gmv/profit、observed_at、completeness_flag。

## 字段标准
- ID存TEXT；金额显式标币种；百分比统一0–100并显式转换。
- 体积L、重量g、尺寸cm；时间UTC存储。
- 0与NULL严格区分；原始字段不得被派生字段覆盖。
- 每个派生字段保留formula_version、computed_at、input_snapshot_id。
- P6与P7均为28天，但快照日分别2026-10-30与2026-10-29，不能假设窗口完全重合。

## 毛订单与估算净口径
sold_count_gross=soldCount，gmv_gross=gmvSum。
r=nullableRedemptionRate/100。
sold_count_net_est=sold_count_gross*r。
gmv_net_est=sold_count_net_est*avg_price。
净口径为估算值，不是平台直接返回的最终结算收入；报告必须同时展示gross/net_est。

## DRR状态
官方UI定义已确认：推广费用/订购商品价值，含取消和退货，按价格上限计算。状态为SEMANTICS_CONFIRMED / VALUE_QC_REQUIRED。0值保留为0，daysWithTrafarets/P8推广状态辅助核验；极端值单独标记，不作为硬淘汰。CPC出价不等于实际广告花费，正式利润优先用广告账单对账。

## 结单率
nullableRedemptionRate是未取消且未退回的订购商品百分比，不是退货率。1-r是未结单比例，可能混合取消、拒收、未取件、退货等原因；不可直接命名return_rate或当作逆向物流成本。

## 历史快照
同一SKU每日或每周追加，不覆盖旧值。P7按query+snapshot_date保存。P7动态字段精确比较基准未确认，需连续快照验证。