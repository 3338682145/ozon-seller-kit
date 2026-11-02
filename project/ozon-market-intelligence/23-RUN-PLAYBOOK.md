# 23 — OMI 每次运行 Run Playbook

## 启动前必做
1. GitHub读取README、PROJECT-STATUS、DECISIONS、HANDOFF。
2. 读取20号Master Prompt、21号Runtime Manifest、22号Context Persistence。
3. 按任务读取02数据契约、03公式和相关审计/实验文档。
4. Supabase确认项目ID eohvguguegxbhszvssbd及数据库版本。
5. 检查source_snapshots、calculation_runs和目标表行数。

## 标准检查SQL

### 当前快照
SELECT snapshot_id, source_name, source_file, source_sha256, file_bytes,
       snapshot_date, window_days, status, table_counts, imported_at
FROM ozon_meta.source_snapshots
ORDER BY imported_at DESC NULLS LAST;

### 最近计算运行
SELECT run_id, calculation_version, source_snapshot_id, status,
       started_at, completed_at, parameters, validation
FROM ozon_meta.calculation_runs
ORDER BY started_at DESC NULLS LAST
LIMIT 20;

### 原始表行数
SELECT 'blue_v3' AS table_name, count(*) AS rows FROM ozon_raw.blue_v3
UNION ALL SELECT 'category',count(*) FROM ozon_raw.category
UNION ALL SELECT 'dim_cluster',count(*) FROM ozon_raw.dim_cluster
UNION ALL SELECT 'fact_keyword_sku',count(*) FROM ozon_raw.fact_keyword_sku
UNION ALL SELECT 'keyword_p7',count(*) FROM ozon_raw.keyword_p7
UNION ALL SELECT 'keyword_score',count(*) FROM ozon_raw.keyword_score
UNION ALL SELECT 'keyword_seerfar',count(*) FROM ozon_raw.keyword_seerfar
UNION ALL SELECT 'keyword_sku',count(*) FROM ozon_raw.keyword_sku
UNION ALL SELECT 'product_seerfar',count(*) FROM ozon_raw.product_seerfar
UNION ALL SELECT 'query_metrics_v2',count(*) FROM ozon_raw.query_metrics_v2
UNION ALL SELECT 'sku_power',count(*) FROM ozon_raw.sku_power
UNION ALL SELECT 'sku_snapshot_v2',count(*) FROM ozon_raw.sku_snapshot_v2
ORDER BY table_name;

Expected source counts for toys_2026_11_02:
- blue_v3 142
- category 1
- dim_cluster 165
- fact_keyword_sku 177063
- keyword_p7 9979
- keyword_score 2795
- keyword_seerfar 1642
- keyword_sku 177063
- product_seerfar 100
- query_metrics_v2 1642
- sku_power 66352
- sku_snapshot_v2 29823

### 关键唯一性
SELECT count(*) - count(DISTINCT sku) AS duplicate_sku_keys
FROM ozon_raw.sku_snapshot_v2;

SELECT count(*) - count(DISTINCT (keyword,sku)) AS duplicate_keyword_sku_keys
FROM ozon_raw.keyword_sku;

SELECT count(*) - count(DISTINCT (keyword,sku)) AS duplicate_fact_keyword_sku_keys
FROM ozon_raw.fact_keyword_sku;

### 元数据上下文
SELECT context_key, version, source_ref, updated_at
FROM ozon_meta.project_context
WHERE active=true
ORDER BY context_key;

SELECT prompt_version,prompt_name,status,sha256,activated_at
FROM ozon_meta.prompt_registry
ORDER BY created_at DESC;

## Data Gate
- 任一必需表未达到预期行数：标记PARTIAL，停止正式计算。
- 关键唯一键重复：停止，先查导入重复或源数据重复。
- snapshot_id混杂或源SHA不一致：不得混合计算。
- redemption_rate NULL：保留Gross；Net-est排除并报告coverage，不填补。
- p8 position必须限制1..108。
- 所有join必须输出匹配率和未匹配数。

## 正式运行
1. 创建唯一run_id；插入calculation_runs，状态running。
2. 插入run_events记录START、数据Gate结果、输入行数、参数。
3. 使用SQL集合运算在Supabase计算；优先临时表/CTE，必要时建立run_id分区结果表。
4. 将结果写入ozon_analytics，必须带run_id。
5. 验证行数、主键、Gross/Net公式、CR4边界（0–100）、跨簇去重和历史基线。
6. 写入calculation_runs.completed_at、status、validation；写run_events完成事件。
7. 登记artifact_registry中的报告、CSV/Excel和GitHub链接。
8. 更新GitHub PROJECT-STATUS、HANDOFF和对应报告，并读回。

## 失败恢复
- 不覆盖旧run_id结果。
- 失败run标记failed，写明SQL阶段、错误信息和已写入行数。
- 修复后创建新run_id；不要复用失败run_id覆盖历史。
- 如果需要删除失败run的派生数据，先确认仅限该run_id，并保留事件审计。

## 最终报告必须包含
数据源与snapshot_id；run_id；公式版本；数据覆盖率；Gross/Net-est规模；CR4 Gross/Net-est；执行耗时；验证结果；异常/缺失；限制；GitHub报告链接；下一步。


## P6/P7标准事实层检查SQL
```sql
SELECT 'fact_p6_sku_28d' AS table_name,count(*) AS rows,count(DISTINCT sku) AS distinct_entities
FROM ozon_analytics.fact_p6_sku_28d WHERE run_id='p6_p7_foundation_20261102_v1'
UNION ALL
SELECT 'fact_p7_keyword_28d',count(*),count(DISTINCT query)
FROM ozon_analytics.fact_p7_keyword_28d WHERE run_id='p6_p7_foundation_20261102_v1'
UNION ALL
SELECT 'bridge_core_keyword_p7',count(*),count(DISTINCT core_keyword)
FROM ozon_analytics.bridge_core_keyword_p7 WHERE run_id='p6_p7_foundation_20261102_v1';
```
预期：P6 29,823；P7 9,979；关键词映射1,642。映射精确命中当前560条，其余1,082条保留为NO_EXACT_MATCH，禁止填零。检查P6 redemption NULL和P7 dyn NULL/ca语义警告。
