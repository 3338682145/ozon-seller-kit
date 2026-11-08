# 字段字典：观测、平台统计与估算严格区分

| 统一字段 | 上游对应字段 | 口径 | 数据性质 |
|---|---|---|---|
| `ozon_id` | P6/P8 `sku`、Buyer `sku_id` | 以字符串保留 ID | 来源键 |
| `title` | Buyer `title`、PDP `name` | 可能缺失；不能从 SKU 猜标题 | 观测 |
| `price_rub` | Buyer/P8 `price` | 前台挂牌价，不等于成交均价 | 观测 |
| `gross_units_28d` | P6 `soldCount` | 统计周期内毛订单件数 | 平台统计 |
| `gross_gmv_rub_28d` | P6 `gmvSum` | 毛订单 GMV，可能含取消/退货 | 平台统计 |
| `avg_price_rub` | P6 `avgPrice` | 平均订单价，不等于前台价 | 平台统计 |
| `redemption_rate_pct` | P6 `redemptionRate` | 0–100%，缺失保留 NULL | 平台统计 |
| `net_units_est_28d` | `soldCount * redemptionRate / 100` | 非真实结算件数 | **估算** |
| `net_gmv_est_rub_28d` | `net_units_est * avgPrice` | 非最终结算金额 | **估算** |
| `sales_dynamics_raw` | P6 `salesDynamics` | GMV 动态，不得称销量增长 | 平台统计 |
| `drr_raw` | P6 `drr` | 推广比例；异常极值独立 QC | 平台统计 |
| `keyword` | P7 `query`、P8 `kw` | 俄语正规化，原词另存 | 观测键 |
| `position` | P8 `position` | 搜索坑位；无资格时 NULL | 观测 |
| `is_advert` | Buyer/P8 广告标记 | nullable；未知≠自然位 | 观测 |
| `promotion_cpc_rate` | P8 `promotionCpcRate` | 出价≠实际广告费 | 平台统计 |
| `general_popularity` | P8 `generalPopularity` | 热度指标≠销量 | 平台统计 |
| `search_buyers_28d` | P7 `count_28d` | 单词独立搜索买家，跨词不能去重求和 | 平台统计 |
| `zero_result_share` | P7 `zr_share` | 未找到合适商品占比 | 平台统计 |
| `stock_max` | Buyer tile `stock_max` | 最多可购数代理≠实物库存 | 页面代理值 |
| `review_count` | Buyer `reviews_count` | 累计评价数≠月销 | 观测 |
| `seller_id` | Buyer/P8 `sellerId` | nullable 字符串；卖家名不等于 ID | 观测 |

每条标准记录必须带 `source`、`observed_at`、`calculated_at`、`data_type`（observation/platform_stat/estimate）、`dataset_version`、`algorithm_version`，并保留原始数据 hash 与授权来源元信息。此表是字段目标规范，不表示所有端点已经返回了所有字段；未知/缺失必须保留 NULL。