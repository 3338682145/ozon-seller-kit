# 25 — Supabase数据资产与缺口审计（2026-11-02）

## 1. 审计范围与方法

- Supabase项目：eohvguguegxbhszvssbd，PostgreSQL 17.6.1.166。
- 原始快照：toys_2026_11_02_33e5f029；源文件SHA256：33e5f02961c2782cead58e6714266aab6cbddc31e74242f905d2a7ba218502d8。
- 本次只读检查：schema/字段、行数、snapshot_id一致性、NULL、唯一键、跨表关联、历史分析结果对账、索引和Supabase Advisors。
- 未修改原始数据、分析数据、权限或表结构；未创建新的正式计算run_id。

## 2. 当前数据资产

12张raw表合计466,767行，且每张表均只有一个snapshot_id（上述快照）：

| 表 | 行数 | 可直接支持的分析 |
|---|---:|---|
| blue_v3 | 142 | 第三方蓝海候选 |
| category | 1 | 类目映射 |
| dim_cluster | 165 | V1需求簇定义 |
| fact_keyword_sku | 177,063 | Keyword-SKU-Cluster关系 |
| keyword_p7 | 9,979 | P7搜索需求 |
| keyword_score | 2,795 | 关键词评分/派生信号 |
| keyword_seerfar | 1,642 | 第三方关键词指标 |
| keyword_sku | 177,063 | P8搜索货架 |
| product_seerfar | 100 | 商品详情样本 |
| query_metrics_v2 | 1,642 | 历史关键词汇总指标 |
| sku_power | 66,352 | SKU关键词排名表现 |
| sku_snapshot_v2 | 29,823 | P6 SKU×28天交易快照 |

关键键核验：
- sku_snapshot_v2.sku：29,823行、29,823个不同SKU。
- keyword_sku(keyword,sku)：177,063行、177,063个不同组合。
- fact_keyword_sku(keyword,sku)：177,063行、177,063个不同组合。
- 12张raw表全部只含一个snapshot_id，没有发现快照混杂。

## 3. 历史分析数据导入与对账

当前5张历史分析表均已上传完整，关联run_id为market_scale_v2_2026_11_02_70d6db0a：

| 表 | 当前行数 | 验证 |
|---|---:|---|
| cluster_market_165 | 165 | 165个簇聚合值与raw重算对账，0项差异 |
| keyword_market_1642 | 1,642 | 1,642个关键词聚合值与raw重算对账，0项差异 |
| cluster_sku_detail | 40,757 | 与raw构建的(cluster_id,sku)集合完全一致；缺失/多余/值差异均为0 |
| keyword_sku_detail | 177,060 | P8有效position全量覆盖；position、seller、Gross字段一致；有结单率的143,720条关联记录Net值在浮点容差内一致 |
| market_scale_summary | 39 | 已完整上传；本次对14项核心汇总指标从raw重新求值，差异仅为浮点精度 |

keyword_sku_detail中：
- 33,146条Gross为空，均对应P8 SKU未匹配P6。
- 33,340条Net为空，其中33,146条是P6未匹配，194条是P6已匹配但redemption_rate缺失。
- 194条对应126个P6 SKU的结单率缺失在关键词货架上的重复出现。
- 不能把这些NULL补成0或100%。

注意：历史分析表的对账证明已导入历史结果与当前raw快照基本一致，不等于已在Supabase创建新run_id完成生产重算。

## 4. 数据缺口清单

### 4.1 P6交易数据（29,823 SKU）

| 字段 | 缺失/异常 | 占比 | 影响 |
|---|---:|---:|---|
| redemption_rate | 126 | 0.42% | Net-est覆盖率需单独报告；Gross不受影响 |
| create_date | 105 | 0.35% | new_top10需排除无上架日期SKU |
| volume | 3 | 0.01% | 少量SKU物流体积缺口 |
| sales_dynamics | 7,516 | 25.20% | GMV动态字段不完整；且不能当销量增长 |

sold_count、gmv_sum、avg_price在本次NULL/非正值检查中均无缺失。redemption_rate有效值范围0–100，126条NULL保留。P6单期快照没有重量、长宽高的完整字段；P6 volume不能替代重量和尺寸。

DRR有值但需QC：中位数0，P90约19.19，P99约65.51，137条大于100，最大值10,431.14；保留原值、单独标记异常，不直接硬淘汰。DRR不是广告账单实际金额。

### 4.2 P8搜索货架（177,063条原始记录）

- position 1–108有效记录177,060条；另有3条position超出范围，应排除。
- 有48,896个不同SKU；其中29,821个与P6匹配，19,075个不同SKU没有P6交易数据。
- 记录级P8-P6匹配143,914/177,060；不同SKU匹配率约61.0%。两个口径不可混用。
- rating和reviews各有34,499条NULL（19.48%）。
- relevance 177,063条全部NULL，弃用。
- CPC有94,803条NULL：其中“不推广”62,640条全部NULL，符合非推广记录特征；“推广中”114,423条里仍有32,163条CPC为空（28.11%），需要区分接口缺失与投放状态。
- seller_id、price、name、popularity、promo本次检查均无NULL。

### 4.3 P7需求与关键词映射

- P7有9,979条query；count_28d、ca、ord、gmv、no_action_share、zr_share、conv_pct本次检查均无NULL。
- dyn_7d、dyn_28d各有4条NULL；动态字段的统计基准仍未确认。
- 1,642个核心关键词与P7 query只有560个精确匹配。其余不能直接认定为无需求，需做规范化/别名映射并人工抽验。
- 不同关键词的count_28d是独立买家数，跨关键词不可直接相加为去重消费者。

### 4.4 需求簇映射

- V1有165个簇，dim_cluster.members共1,334个关键词成员，无重复成员。
- 1,642个核心关键词中1,334个有簇映射，308个关键词完全未分配。
- fact_keyword_sku有33,204条cluster_id为NULL，对应上述未分配关键词。
- 这会造成需求簇覆盖不完整；必须单列Unclustered池，不能把未分配SKU直接当新蓝海。

### 4.5 产品族、变体与Seller Offer

- 当前没有dim_product_family、bridge_family_sku等L2a产品族映射表。
- product_seerfar只有100条商品详情样本，不能代表全量29,823个P6 SKU或48,896个P8 SKU。
- 100条raw_json均包含weight、dimension、volume、variants和非空variationIds，可从原始JSON提取，优先复用现有数据。
- 结构化brand列100条全部为空；raw_json中的brandName只有29/100非空。
- 这100条raw_json未发现barcode或model字段。
- 当前raw表没有完整买家端全量变体矩阵、所有跟卖卖家报价/企业凭据、评价正文/差评、stock_max历史序列。P8 seller_id只代表搜索货架记录中的卖家信息，不能替代全量Seller Offer关系。

### 4.6 利润与供应链

当前raw schema中没有已导入的采购报价、物流费率、平台佣金/支付费率、实际广告账单、税费及取消/拒收/退货原因明细表。因此：
- 1688采购价、MOQ、国内运费、包装成本缺失；
- 重量/尺寸只有100条Seerfar详情样本，覆盖不足；
- 物流渠道费率、体积重规则、有效期缺失；
- 佣金23%仍是人工假设，不可当作事实；
- CPC/CPO是出价，DRR是比例信号，都不能代替实际广告账单。

当前可以做成本情景分析，但不能输出精确净利润和ROI。

### 4.7 时间序列与预测

当前raw表只有一个snapshot_id。P6为2026-10-30的28天快照，P7快照日为2026-10-29。没有连续P6/P7历史快照，无法验证真实销量增长、季节性或训练可靠的30/60/90天预测。P6 sales_dynamics是GMV动态，P7 dyn_7d/dyn_28d基准未确认，Seerfar growth_30d是第三方估算，均不能替代连续同口径历史序列。

## 5. 性能与安全结构

### 性能
- 当前12张raw表没有索引/主键；pg_indexes检查到的索引主要是analytics/meta主键。
- GitHub旧脚本rebuild_market_scale.py使用SQLite + Pandas，多次读取/merge并按组循环聚合，不适合作为Supabase正式计算架构。
- 推荐索引候选：sku_snapshot_v2(snapshot_id,sku)、keyword_sku(snapshot_id,keyword,position,sku)、fact_keyword_sku(snapshot_id,cluster_id,keyword,sku)、keyword_p7(snapshot_id,query)、keyword_seerfar(snapshot_id,query)、sku_power(snapshot_id,sku)。
- 推荐将P8过滤、P6派生字段和SKU关联一次性形成run级基础明细，再用集合式GROUP BY生成关键词、簇、卖家汇总；不要把大表拉到本地Pandas循环计算。
- 本次未创建索引或修改SQL生产流程；需要先设计并测量EXPLAIN (ANALYZE, BUFFERS)。

### 安全
- Supabase表清单提示19张raw/analytics/meta表未启用RLS。
- 本次另查到anon/authenticated对三个业务schema均无USAGE权限，且对ozon_raw.keyword_sku无SELECT权限；当前未发现这两个角色通过该路径可直接读取数据。
- 仍需将RLS作为纵深防护治理项；不能直接无策略启用RLS，以免阻断合法访问。应先确认服务端访问方式和策略，再安排变更。

## 6. 建议执行顺序

1. **先复用现有数据**：把历史分析表视为baseline，采用Supabase SQL重建run级基础明细与聚合，不再重新上传相同CSV。
2. **先解决性能**：对关键raw关联键设计索引，做执行计划和耗时基准；索引DDL经确认后再执行。
3. **补映射**：整理308个未分配关键词和P7精确匹配缺口；保持V1冻结，映射不等于自动合并。
4. **建设L2a**：从100条raw_json提取已有变体证据，再对剩余高价值SKU补采商品详情、变体和Seller Offer。
5. **补经营成本**：采购报价、物流费率、佣金、广告账单和税费。
6. **建立时间序列**：持续采集同口径P6/P7快照，积累后再开展30/60/90天预测与回测。

## 7. 本轮结论

- 原始12张表已完整；5张历史分析表已全部上传。
- 165簇、1,642关键词聚合结果与raw重算对账通过；簇SKU明细和关键词SKU明细行数完整。
- 当前最关键缺口不是P6基础销量字段，而是P6/P8未匹配SKU、308个未分配关键词、L2a产品族/全量Seller Offer、供应链成本和连续时间序列。
- 当前最直接的性能问题是raw表缺少索引，以及旧脚本使用SQLite/Pandas多轮merge和分组循环。
- 本轮为只读审计，没有创建正式计算run_id，也没有改动任何生产数据或权限。
