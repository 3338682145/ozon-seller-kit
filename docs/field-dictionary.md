# 字段字典：观测、平台统计与估算严格区分

本表区分上游**原始键/路径**、旧代码的**解析归一键**与目标统一字段；不能直接用解析键去索引原始响应。以下是目标规范，不表示新 Runtime 已实现或 P7 已有在线接口。

| 统一字段 | 上游原始键/路径 | 当前解析键 / 目标映射 | 口径与限制 | 数据性质 |
|---|---|---|---|---|
| `ozon_id` | P6/P8 `sku`；Buyer tile `sku` / `id` | Buyer `sku_id` → `ozon_id` | 以字符串保存 ID | 来源键 |
| `title` | Buyer `cellTrackingInfo.title`、PDP `name` | Buyer `title` | 缺失保留 NULL；不能按 SKU 猜标题 | 观测 |
| `price_rub` | Buyer `cellTrackingInfo.price` 或 `mainState[].priceV2.price`；P8 `price` | Buyer `price` → `price_rub` | 前台挂牌价，不是成交均价 | 观测 |
| `gross_units_28d` | P6 `soldCount` | `gross_units_28d` | **仅**当数据对应窗口确认为 28 天；weekly 等其他窗口须另存 `period_days`，不得混写 | 平台统计 |
| `gross_gmv_rub_28d` | P6 `gmvSum` | `gross_gmv_rub_28d` | 同上，金额可能含取消/退货 | 平台统计 |
| `avg_price_rub` | P6 `avgPrice` | `avg_price_rub` | 毛订单均价，不等于前台价；保留窗口信息 | 平台统计 |
| `redemption_rate_pct` | **P6 `nullableRedemptionRate`** | 旧 SQLite `sku.redemption_rate`；目标 `redemption_rate_pct` | 0–100%；NULL 表示未知，**不得按 0 或 100% 回填** | 平台统计 |
| `net_units_est_28d` | P6 `soldCount`、`nullableRedemptionRate` | `soldCount * nullableRedemptionRate / 100` | 非真实结算件数；任何输入缺失则 NULL；仅已核实 28 天窗口有效 | **估算** |
| `net_gmv_est_rub_28d` | P6 `avgPrice` + 上行输入 | `net_units_est_28d * avgPrice` | 非最终结算金额；输入缺失则 NULL | **估算** |
| `sales_dynamics_raw` | P6 `salesDynamics` | `sales_dynamics_raw` | GMV 动态，不得称销量增长 | 平台统计 |
| `drr_raw` | P6 `drr` | `drr_raw` | 推广比例；异常极值须独立 QC | 平台统计 |
| `keyword` | P7 历史 `query`、P8 调用参数 `keyword` | P8 输出 `kw` → `keyword` | 俄语正规化，原词另存；P7 在线 Adapter 未实现 | 观测键 |
| `position` | P8 `position` | `position` | 搜索坑位；无资格时 NULL | 观测 |
| `is_advert` | Buyer `trackingInfo.click.custom.advertLite`；P8 具体广告键待样本核对 | Buyer `is_advert` | **目标为 nullable**；旧 `collector.py` 用 `bool(...get('advertLite'))`，会把缺失错误压成 False，新 Adapter 不得照搬 | 观测 |
| `promotion_cpc_rate` | P8 `promotionCpcRate` | `promotion_cpc_rate` | 出价不等于实际广告费 | 平台统计 |
| `general_popularity` | P8 `generalPopularity` | `general_popularity` | 热度指标不等于销量 | 平台统计 |
| `search_buyers_28d` | P7 历史表 `count_28d` | `search_buyers_28d` | 单词独立搜索买家；跨词不可去重求和；在线 P7 未实现 | 平台统计 |
| `zero_result_share` | P7 历史表 `zr_share` | `zero_result_share` | 未找到合适商品占比 | 平台统计 |
| `stock_max` | Buyer `multiButton.ozonButton.addToCart.quantityButton.maxItems`（含 fallback） | Buyer `stock_max` | **购物车最多可购买数代理，不是经过核验的实物库存** | 页面代理值 |
| `review_count` | Buyer `cellTrackingInfo.reviewCount`（或 `labelListV2`） | Buyer `reviews_count` → `review_count` | 累计评价数不等于月销量 | 观测 |
| `seller_id` | Buyer/P8 卖家标识字段（路径需按样本确认） | `seller_id` | nullable 字符串；卖家名称不可替代 ID | 观测 |

每条标准记录须带 `source`、`observed_at`、`calculated_at`、`data_type`（observation/platform_stat/estimate）、`dataset_version`、`algorithm_version` 和已核实的 `period_days`，并保留原始数据 hash 与授权来源元信息。未知/缺失必须保留 NULL；旧 README 的库存断言不能覆盖本字段规范。
