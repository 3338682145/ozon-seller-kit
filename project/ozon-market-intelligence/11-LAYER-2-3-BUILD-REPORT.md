# 11 — 第二层产品需求簇与第三层SKU实体构建报告（2026-11-02）

## 结论
已基于新版 toys.db 的 dim_cluster、fact_keyword_sku、keyword_sku、sku_snapshot_v2 建立第二层165个产品需求簇和第三层48,898个SKU实体，以及多对多关联桥表。

**术语边界：** 本次第二层沿用现有165个关键词/需求簇定义，是“产品需求簇/市场主题”，不是165个已完成精确同款识别的商品族。一个簇内部可能有多种形态，一个SKU也可能跨多个需求簇。未来接入variantId、商品标题和属性后，应在需求簇与SKU之间补充精确产品族/变体族层。

## 第二层：dim_product_cluster
- 165个簇全部建立。
- 1,334个关键词绑定cluster，形成1,334条cluster-keyword关系。
- 每簇计算簇内去重SKU数、p6匹配SKU数、簇内去重销量/GMV、加权成交价、卖家数、跨簇重叠SKU数。
- 簇内销量按distinct SKU统计；同一SKU若出现在多个簇，会在每个簇分别出现，因此跨簇求和不可作为总市场规模。

## 第三层：dim_sku
- 由keyword_sku/fact_keyword_sku生成48,898个唯一SKU实体。
- 29,823个SKU能关联p6快照；19,075个仅有p8搜索位映射、未匹配p6，保留为未知销量，不当作零销量。
- p8 seller_id保留为p8_seller_id；p6 seller_id作为主seller_id，缺失时回填p8 seller id。48,898个SKU的p8 seller_id均非空。
- 每个SKU记录cluster_count、cluster_ids、keyword_count、best_position，以及p6销量、GMV、成交价、库存、体积、DRR原值等。
- DRR状态统一为SUSPECT_QUARANTINED，仅保留原值，不参与硬过滤和正式单点利润。

## 关联桥表
| 表 | 行数 | 说明 |
|---|---:|---|
| bridge_cluster_keyword | 1,334 | cluster ↔ keyword |
| bridge_cluster_sku | 40,759 | 去重后的cluster ↔ SKU关系 |
| bridge_sku_keyword | 177,063 | 完整keyword ↔ SKU关系 |

- 关键词-SKU原始映射177,063条，1,642个关键词，48,898个不同SKU。
- 143,859条映射有cluster_id；33,204条映射cluster_id为空。
- 有cluster归属的不同SKU并集29,859；其中5,267个SKU跨多个非空cluster。
- 有cluster归属且p6可匹配SKU 19,942；cluster映射中p6未匹配9,917个。
- p6总SKU 29,823，其中9,881个没有任何非空cluster归属。
- 未归类映射保留，不丢弃。

## 去重市场规模口径
- 各簇p6销量逐簇求和：5,764,712件（簇级重叠口径，不可作为总市场销量）。
- 所有簇SKU合并后全局去重p6销量：1,955,072件（仅覆盖已归属簇且可匹配p6的SKU）。
- 全部p6 SKU销量：3,332,338件。
- 因SKU跨簇，cluster总量不具备可加性；全市场总量必须按全局唯一SKU计算，并把未归类SKU单独列示。

## 按簇内去重p6销量排序的前10簇
| Cluster | 主词 | 簇内SKU | p6 SKU | p6销量 | p6 GMV RUB | ASP RUB | 卖家数 | 跨簇SKU |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| C002 | сквиш | 2,715 | 2,221 | 643,286 | 147,472,804 | 229.2 | 1,233 | 1,552 |
| C001 | сквиш масло | 3,068 | 2,075 | 405,210 | 80,123,938 | 197.7 | 1,308 | 1,187 |
| C003 | дамплинг | 777 | 677 | 349,327 | 63,627,953 | 182.1 | 395 | 427 |
| C005 | спинер | 1,399 | 1,183 | 289,668 | 68,659,878 | 237.0 | 733 | 674 |
| C004 | клавиатура антистресс | 1,037 | 866 | 275,150 | 49,751,907 | 180.8 | 560 | 424 |
| C090 | игрушка антистресс сквиш | 200 | 194 | 263,429 | 49,145,277 | 186.6 | 95 | 199 |
| C007 | нидл сквиш | 724 | 646 | 237,884 | 46,608,589 | 195.9 | 360 | 481 |
| C033 | сквиш большой | 240 | 237 | 222,863 | 42,468,739 | 190.6 | 111 | 238 |
| C103 | сквишь | 153 | 151 | 182,139 | 30,505,182 | 167.5 | 67 | 153 |
| C162 | сквиш котик антистресс | 154 | 150 | 126,613 | 24,042,098 | 189.9 | 63 | 154 |

注：这里的销量是p6快照窗口的sold_count，报告中不将其擅自称为28天，统计窗口须按源字段口径确认。

## 数据库与验收
派生数据库：ozon-product-layers.db
SHA256：4f244935cc3edbd642fe0621d04da80f9f8501dcd27c9fa577ed5f19c06ed441
大小：64,569,344 bytes
SQLite integrity_check：ok
校验：165 clusters、48,898 unique SKU、177,063 keyword-SKU links、40,759 cluster-SKU links、1,334 cluster-keyword links；关键ID无空值，两个桥表无重复主键。

## 文件输出
本地归档包含：
- ozon-product-layers.db
- dim_product_cluster.csv（165簇）
- bridge_cluster_sku.csv（40,759簇-SKU关系）
- dim_sku.csv（48,898 SKU实体）
- bridge_cluster_keyword.csv（1,334簇-关键词关系）
- bridge_sku_keyword.csv（177,063关键词-SKU关系）
- manifest.json及build_product_layers.py

## 下一步
1. 接入Drive bestsellers_latest.parquet（1,962,354行）补齐title、variantId、图片、真实sellerId、重量和尺寸；其快照2026-10-21早于p6 2026-10-30，不能无条件混用时间变化字段。
2. 基于商品身份、variantId、标题、属性和图片，建立exact/close产品族映射；对需求簇内部的多产品形态继续拆分。
3. 将keyword_p7与Seerfar词做规范化匹配，形成需求簇→产品族→SKU→搜索行为链路。
4. DRR继续隔离；在字段口径核验前不进入正式利润单点结果。
