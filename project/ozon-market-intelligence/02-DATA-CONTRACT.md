# 02 — 数据字典与数据契约

## 数据源
| 来源 | 粒度 | 核心字段 | 性质与限制 |
|---|---|---|---|
| p6 | SKU×快照 | sold_count, gmv_sum, avg_price, drr, volume, stock, create_date, redemption_rate, promo_revenue_share | 卖家后台快照；单期不是时间序列 |
| p8 | keyword×position×SKU | position, price, seller_id, promo, cpc | 每词最多108位 |
| P7 | query×月份/快照 | count_28d, dyn_7d, dyn_28d, no_action_share, zr_share, ord, gmv, ca | 搜索需求，不等于购买 |
| Seerfar | keyword×快照 | search_volume, growth_30d, conv_pct, competing_products | 第三方估算，需异常值治理 |
| 1688/供应链 | SKU/报价×时间 | purchase_price, MOQ, domestic_shipping, weight, dimensions | 报价有有效期 |
| 物流费率 | 渠道×计费档 | base, per_gram, volumetric_divisor, service tier | 2026-04-15费率需重新确认 |

## 核心事实表
### fact_sku_snapshot
sku TEXT、snapshot_date、period_start、period_end、period_days、sold_count、gmv_sum_rub、avg_price_rub、volume_l、weight_g、length_cm、width_cm、height_cm、drr_pct、promo_revenue_share_pct、stock_units、accessibility_days、rating、reviews、create_date、redemption_rate_pct、commission_pct、category3_id、category3、seller_id、brand、source、collected_at、raw_payload_ref。

### fact_keyword_position
keyword、snapshot_date、position、sku、seller_id、listed_price_rub、cpc_rub、is_promoted、create_date、join_status、missing_reason。

### fact_keyword_demand
query、snapshot_date、period_days、count_28d、dyn_7d_pct、dyn_28d_pct、no_action_share_pct、zero_result_share_pct、orders、gmv_rub、add_to_cart、item_views、source、quality_flag。

### 产品族映射
dim_product_family：family_id、canonical_name_cn/ru、category3_id、family_scope、match_confidence、match_method、reviewed_by、ip_risk_status。
bridge_family_sku：family_id、sku、relation_type、confidence、evidence_json、valid_from、valid_to。
bridge_family_keyword：family_id、keyword、relevance_score、intent_type、reviewed_flag。

### 成本与预测表
fact_cost_quote：entity_id、quote_date、valid_until、supplier_url、purchase_cost_cny、MOQ、domestic_shipping_cny、packaging_cny、weight/dimensions、quote_confidence。
dim_logistics_rate：channel、service_level、tier、base_fee、rate_per_g、volumetric_divisor、weight/value cap、effective dates、source.
fact_forecast：entity_id、origin_date、horizon_days、model_version、scenario、forecast_units/gmv/profit、lower/upper bound、input snapshot IDs。
fact_actual_outcome：entity_id、target_date、horizon_days、actual_units/gmv/profit、observed_at、completeness_flag。

## 字段标准
- ID存TEXT；金额显式标币种；比例统一0–100，公式中除以100。
- 体积L、重量g、尺寸cm；时间统一UTC存储。
- drr=0表示未投放，NULL才表示缺失。
- 所有派生字段保留formula_version、computed_at、input_snapshot_id。
- 保存period_start/end，不能只保存一个模糊的“月销”。

## redemption_rate待核验
用户业务解释为成功结算率，1-redemption_rate可表示未成功结算比例。正式上线前需核实分母是否发货订单、分子是否最终结算订单，以及未结算是否只包含退货，还是也包含取消、拒收、未取件、配送失败。若含多种失败原因，字段命名为non_settlement_rate，不得直接称return_rate。若能取得退款/退货件数及逆向物流费用，应独立建模。

## 历史快照
同一SKU每日或每周追加，不覆盖旧值。P7按query+month+snapshot_date保存。只有同一统计窗口、同一口径的两期数据才能计算增速。