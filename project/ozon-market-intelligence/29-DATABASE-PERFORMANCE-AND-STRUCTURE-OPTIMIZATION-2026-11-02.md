# 29 — Supabase性能与数据结构优化报告（2026-11-02）

## 1. 结论
目前数据规模不是主要瓶颈。原始P6约29.8k SKU、P7约10k query、P8约177k keyword-SKU关系，PostgreSQL完全可以直接处理。主要瓶颈是原始核心表此前没有索引、反复全表扫描、多个事实粒度未区分，以及每次工作被拆成大量串行工具调用。

本轮已在Supabase完成索引、自然主键、P8标准事实表、关键词市场宽表和类目视图建设。没有删除或覆盖任何原始行。

## 2. 性能证据
优化前pg_stat_user_tables累计观察到：
- ozon_raw.keyword_sku：59次seq_scan，seq_tup_read约6,866,331，idx_scan为NULL。
- ozon_raw.fact_keyword_sku：34次seq_scan，seq_tup_read约4,687,638，idx_scan为NULL。
- ozon_raw.sku_snapshot_v2：64次seq_scan，seq_tup_read约1,580,619，idx_scan为NULL。
这些统计是数据库累计计数，说明访问路径以顺序扫描为主。

优化后EXPLAIN ANALYZE：
- 单关键词P8检索：Index Only Scan，返回108行，Execution Time约13.586ms，Heap Fetches=0。
- curated P8事实表同类查询：Index Scan，返回108行，Execution Time约14.765ms。
- 按category3_id+keyword过滤：Index Scan，返回103行，Execution Time约12.778ms。
以上是单次查询测试，不代表所有SQL都在该时间内，也不是严格的前后压测倍数。当前数据库内单次查询已很快；ChatGPT整体等待时间还包括工具往返、上下文恢复、多个串行SQL调用和结果解释时间。

## 3. 原始数据结构审计

### 3.1 核心事实表
| 表 | 行数 | 自然粒度 |
|---|---:|---|
| sku_snapshot_v2 | 29,823 | snapshot × SKU（P6） |
| keyword_p7 | 9,979 | snapshot × query（P7） |
| keyword_sku | 177,063 | snapshot × keyword × SKU（P8货架） |
| fact_keyword_sku | 177,063 | snapshot × keyword × SKU（簇/ESI扩展） |
| sku_power | 66,352 | snapshot × SKU × cluster_id（不是SKU唯一） |

keyword_sku与fact_keyword_sku当前177,063组(keyword,sku)完全匹配，可作为P8货架和簇/ESI扩展的1:1连接。position>108有3条，正式P8分析排除。

### 3.2 sku_power特别警告
- 66,352行，但只有48,898个不同SKU。
- 25,593行cluster_id为NULL。
- 唯一粒度为snapshot × sku × cluster_id（NULL cluster使用独立部分唯一索引）。
不得把sku_power行数当成SKU数；若按SKU统计，必须先聚合/去重。该表目前是唯一仍没有传统Primary Key的raw表，因为cluster_id可为空且一个SKU可关联多个cluster。

### 3.3 P6跨类目
P6是多类目商品池。当前快照29,823 SKU，378个category3。抗压玩具使用category3_id=92811。所有核心市场分析必须明确类目范围，不能直接对全P6聚合后称为抗压玩具市场。

## 4. 已实施的结构优化

### 4.1 Raw自然主键
已对11张raw表中的10张建立复合主键（category也使用snapshot_id主键）：
- blue_v3(snapshot_id,query)
- dim_cluster(snapshot_id,cluster_id)
- fact_keyword_sku(snapshot_id,keyword,sku)
- keyword_p7(snapshot_id,query)
- keyword_score(snapshot_id,query,version)
- keyword_seerfar(snapshot_id,query)
- keyword_sku(snapshot_id,keyword,sku)
- product_seerfar(snapshot_id,sku)
- query_metrics_v2(snapshot_id,keyword)
- sku_snapshot_v2(snapshot_id,sku)
- category(snapshot_id)
sku_power采用部分唯一索引保留nullable cluster grain，不强制伪造单一SKU主键。

### 4.2 Raw复合索引
按常用查询路径建立：
- P8：snapshot_id + keyword + position，并INCLUDE sku/seller_id/price；另建snapshot+sku反向查找。
- Keyword-SKU扩展：snapshot+cluster+sku及snapshot+sku。
- P6：snapshot+category3_id+sku、snapshot+seller_id。
- P7：snapshot+query唯一索引。
- SKU power：snapshot+cluster+sku及部分唯一索引。
- 所有核心表已ANALYZE更新统计信息。

### 4.3 Curated Analytics层
新建：
1. fact_p8_keyword_sku_108：177,060行，position 1–108；连接P8、V1 cluster/ESI和P6 SKU属性。
2. bridge_keyword_cluster_v1：1,642行，一个关键词最多一个V1 Primary；1,334已归簇，308未归簇。
3. mart_keyword_market_base_v1：1,642行，每关键词一行，整合P7精确匹配字段、P8覆盖和P6类目构成。

新增视图：
- v_p6_antistress_28d_v1：P6 category3_id=92811。
- v_p8_antistress_top108_v1：P8前108位且P6匹配类目为抗压玩具的货架子集。
- v_keyword_market_scope_v1：关键词市场宽表。
- v_sku_cluster_power_source_v1：明确SKU power的SKU×cluster粒度。

新表已启用RLS；视图使用security_invoker，不对anon/authenticated开放schema权限。

## 5. 关键质量结果
- P8 top108：177,060条唯一keyword-SKU对；排除3条position>108。
- P8 top108与P6匹配：143,917行（81.28%）；未匹配33,146行（18.72%）。未匹配不等于零销量。
- 1,642关键词V1 Primary：1,334已分配，308未分配。
- P7 exact query匹配：560/1,642（34.10%）；1,082未精确匹配，尚未做俄语规范化/别名映射。
- 关键词类目构成（仅P8 top108且P6匹配SKU）：
  - 881个关键词：匹配SKU全部属于抗压玩具。
  - 751个关键词：同时包含抗压玩具和其他类目。
  - 9个关键词：匹配SKU不属于抗压玩具。
  - 1个关键词：没有P6匹配。
- 抗压玩具P8前108可见货架：114,441行、16,037个不同SKU；P6类目快照有16,039 SKU，其中2个没有出现在P8前108可见集合中。

注意：每个关键词下SKU会重复出现，mart_keyword_market_base_v1中的各关键词P6销量/GMV不可跨关键词直接求和。

## 6. 数据分层规范（从本轮起执行）
- ozon_raw：原始快照、append-only；不直接清洗覆盖。
- ozon_analytics.fact_*：标准事实表，明确粒度、单位、snapshot_id、run_id。
- ozon_analytics.bridge_*：实体关系桥表（keyword-cluster、keyword-P7 alias等）。
- ozon_analytics.dim_*：规范化维度（未来建立产品族、卖家、类目）。
- ozon_analytics.mart_*：一行一个分析实体的宽表/主题数据集。
- ozon_analytics.v_*：安全的查询视图，默认类目过滤明确。
- ozon_meta：snapshot、run、decision、prompt、context、events、artifact、labels。

Raw保留来源字段；规范化字段放Analytics，不在原始表上做破坏性UPDATE。所有事实表必须注明grain，所有金额字段注明币种，所有百分比注明单位，所有派生值注明公式版本。

## 7. 下一阶段性能策略
1. 一次任务尽量合并为一个或少数几个SQL批次，避免每一步单独工具往返。
2. 大表先在Supabase内聚合，返回摘要，不把17万行拉回聊天。
3. V2关键词相似度使用fact_p8的SKU倒排索引：按SKU连接出共现关键词对，再计算Overlap/Jaccard/Top30/Rank-weighted/IDF；不做1,347,261次独立SQL请求。
4. 后续新快照只增量计算新增/变化的keyword-SKU和SKU，不重算全部历史。
5. 索引使用情况观察一段真实工作负载后再清理；刚建索引被Advisor标记unused不代表无用。
6. 向量数据库暂不解决本轮瓶颈；先用关系索引和倒排共现做精确SKU相似度，向量检索只在L2a文本/图片候选召回阶段评估。

## 8. 本轮运行
- run_id：market_core_v1_20261102
- source_snapshot_id：toys_2026_11_02_33e5f029
- status：completed_with_data_quality_warnings
- SQL脚本：
  - sql/optimize_raw_schema_indexes_v1.sql
  - sql/build_p8_curated_fact_v1.sql
  - sql/build_keyword_market_mart_v1.sql
- 历史raw数据未删除，历史分析表未覆盖。
