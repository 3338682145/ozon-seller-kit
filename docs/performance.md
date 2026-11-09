# 性能基准和生产压测约束

只有 Mock 数据与本地处理逻辑可在当前环境执行；HTTPX/Playwright、Crawlab、Redis、PostgreSQL、ClickHouse、MinIO 和 Ozon 前台吞吐 **未压测**。

本地基准：`python scripts/benchmark_mock.py --rows 5000`，固定数据集为 5,000 条合成 SKU/关键词/价格/排名记录，顺序执行 `clean_records → keyword_sku_metrics → MemoryFactsSink`。`Silver rows/s` 仅代表本机器单进程清洗的速度，不能替代真实来源许可上限。

生产压测完成的先决条件：确认合法授权、真实端点许可频率与 burst、最低权限 Secret、监控/告警、测试环境隔离；固定数据集和版本。压测按控制面 PG 写入、队列延迟、并发 lease、Redis Lua token bucket、MinIO raw hash、ClickHouse 批写/FINAL 对账分别验收，不对 Ozon 使用未经批准的增速或压力测试。

## 本地测量输出（非 SLA）

```json
{
  "scope": "SYNTHETIC_ONLY_NOT_SOURCE_BENCHMARK",
  "python": "3.13.5",
  "rows": 5000,
  "silver_seconds": 0.01921,
  "silver_rows_per_second": 260287,
  "gold_and_memory_sink_seconds": 0.155534,
  "fact_product_daily_rows": 5000,
  "fact_serp_observation_rows": 5000,
  "errors": 0
}
```
