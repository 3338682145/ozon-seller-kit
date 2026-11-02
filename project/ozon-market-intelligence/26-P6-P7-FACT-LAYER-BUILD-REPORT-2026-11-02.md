# 26 — P6/P7标准事实层构建与数据质量报告（2026-11-02）

## 运行信息
- Supabase project_id：eohvguguegxbhszvssbd
- source_snapshot_id：toys_2026_11_02_33e5f029
- source SHA256：33e5f02961c2782cead58e6714266aab6cbddc31e74242f905d2a7ba218502d8
- run_id：p6_p7_foundation_20261102_v1
- formula_version：p6-p7-foundation-v1
- 状态：completed_with_data_quality_warnings
- P6快照：2026-10-30，28天
- P7快照：2026-10-29，28天

## 1. 构建结果
已在ozon_analytics新建并写入4张表：
1. fact_p6_sku_28d：29,823行，29,823个唯一SKU。
2. fact_p7_keyword_28d：9,979行，9,979个唯一query。
3. bridge_core_keyword_p7：1,642行，连接P8核心关键词与P7 query。
4. p6_p7_quality_audit：3行，记录P6、P7和关键词映射的数据质量检查。

新表已启用RLS；索引覆盖snapshot_id、sku、seller_id、category3_id和query。

可复现SQL：sql/build_p6_p7_foundation_v1.sql

## 2. P6 SKU事实层
### 正式字段
- Gross：gross_units_28d = raw sold_count。
- Gross GMV：gross_gmv_rub_28d = raw gmv_sum。
- avg_price_rub保留原始P6均价。
- redemption_rate_pct保留原始百分比。
- Net估算：net_units_est_28d = gross_units_28d × redemption_rate_pct / 100。
- Net GMV估算：net_gmv_est_rub_28d = net_units_est_28d × avg_price_rub。
- redemption_rate为NULL时，Net字段保留NULL；状态标记MISSING_REDEMPTION_RATE。
- sales_dynamics_gmv_raw、drr_raw、库存、广告天数、促销占比等保留原始值，不擅自修正。

### 实际核验
| 指标 | Supabase结果 |
|---|---:|
| SKU行数 | 29,823 |
| 唯一SKU | 29,823 |
| redemption_rate缺失 | 126 |
| Net估算覆盖率 | 99.5775% |
| Gross销量28天 | 3,332,338 |
| Net销量估算28天 | 2,964,159.549 |
| Gross GMV | 1,318,910,734.23 RUB |
| Net GMV估算 | 1,140,330,863.25 RUB |
| redemption_rate范围 | 0–100 |
| 超范围/负销量异常 | 0 |

Net GMV为按毛订单均价估算的妥投GMV，不是Ozon最终结算金额。126个缺失结单率SKU不填0、不填100%，只保留Gross并排除于Net估算。

## 3. P7关键词事实层
### 正式字段
- search_buyers_28d：count_28d，按每个query保留独立搜索买家数。
- dyn_7d_raw、dyn_28d_raw：保留平台原始动态值，未验证比较基准。
- uniq_sellers：卖家数。
- zr_share_pct、no_action_share_pct、conv_pct：按原始百分比保留。
- search_order_gmv_raw_rub：P7原始GMV。
- ord_raw、ca_raw：原值保留，不对不确定单位做派生。
- avg_price_raw_rub、items_views_raw、group_name、type_id等保留。

### 实际核验
| 指标 | Supabase结果 |
|---|---:|
| P7 query行数 | 9,979 |
| 唯一query | 9,979 |
| 快照日期 | 2026-10-29 |
| count_28d范围 | 625–394,585 |
| dyn_7d缺失 | 4 |
| dyn_28d缺失 | 4 |
| dyn_7d范围 | -100至122,000 |
| dyn_28d范围 | -89至401,100 |
| no_action_share范围 | 6.3%–100% |
| zr_share范围 | 0%–93.7% |
| conv_pct范围 | 0%–51.6% |
| ca_raw范围 | 0–78.87 |

### 重要语义风险
- count_28d是query级独立搜索买家数；同一个买家可能搜索多个词，不能跨query直接相加成市场独立消费者。
- dyn_7d/dyn_28d存在极端值且各4条NULL；比较基准未核实。只保留原值，不直接作为标准环比或销量增长。
- ca字段在历史字段解释中被描述为加购人数，但数据库实际类型为double precision，值域0–78.87，样例呈小数。字段单位/分母存在语义不一致风险。本版仅存ca_raw，标记UNIT_UNVERIFIED_RAW_ONLY，不将其当加购人数、不做人数加总。需回到Ozon原生UI tooltip/原始接口核验。
- no_action_share代表搜索后无点击比例，不是“假需求”结论。
- zr_share代表零结果占比，可作为潜在供给缺口信号，但需结合真实订单与转化验证。

## 4. P7与1,642个核心关键词映射
以P8 position 1–108中出现的1,642个核心关键词，与P7 9,979个query做精确字符串匹配：
- 精确匹配：560个。
- 无精确匹配：1,082个。
- 精确匹配覆盖：34.1048%。

无精确匹配不等于没有搜索需求。尚未做俄语大小写、ё/е、词形、单复数、拼写变体、词序和语义别名映射。后续需建立规范化和人工审核映射，不允许直接把未匹配填0。

## 5. 时间和实体边界
- P6快照2026-10-30，P7快照2026-10-29；两者都是28天窗口，但起止日期不能假设完全相同。
- P6是SKU×快照事实；P7是query×快照事实。两者粒度不同，不得把P7搜索人数加到P6商品销量。
- P7 query层与P8核心keyword存在多对多/别名可能，当前bridge仅做精确匹配。

## 6. 安全状态
- 新建的4张分析事实/桥接/质量表已启用RLS。
- Supabase权限核验：anon/authenticated对ozon_raw、ozon_analytics无schema USAGE及相关SELECT权限。
- Supabase Advisor仍提示19张既有raw/历史analytics表RLS disabled。当前SQL权限检查未发现anon/authenticated直接访问，但建议后续按私有数据访问模型做RLS纵深加固；不能在未确定访问策略前随意开放表。

## 7. 下一步
1. 核实P7 ca的官方单位和计算分母。
2. 建立keyword normalization/alias mapping，把560精确匹配扩展到有证据的别名匹配。
3. 基于P6/P7 facts与P8货架建立统一关键词市场宽表，但严格保留不同粒度。
4. 在此基础上计算市场规模、Seller CR4、max_slot30/new_top10和Entry。
5. 收集连续快照后再建增长预测，单期P6/P7不能当历史趋势。
