# Ozon Collection Runtime · Engineering Overlay

可审计、遵守授权范围、默认 Mock 的数据采集与运维工程层，设计用于**叠加** `3338682145/ozon-seller-kit`，不是替代其已有 Seller/Buyer 解析代码。

- 调度：Crawlab 批次管理（可选 profile）→ FastAPI → PostgreSQL Outbox → Redis Streams 优先级消费 / XAUTOCLAIM / 租约 / DLQ。
- 采集：统一五阶段 Adapter；默认 Mock；Seller P6/P8/CJM 复用上游高层请求构造但改为失败即停的安全 HTTPX Transport；P7 明确缺口；Buyer 仅获准离线快照解析。
- 数据：MinIO Bronze，Polars/PyArrow Silver，PostgreSQL Master/Keyword-SKU，ClickHouse Gold，来源/版本与 NULL/估算值区分。
- 运维：只读优先的 Collector Ops / Database Ops Agent MCP 工具、人工审批、固定 runbook、Prometheus/Loki/Grafana/Alertmanager 示例配置。

## 开发验收

```bash
python -m pip install -e '.[test]'
python -m pytest -q
python scripts/demo_smoke.py
```

## Docker Mock 全链路

```bash
bash scripts/bootstrap.sh
python scripts/compose_smoke.py
```

以上 `compose_smoke.py` 需要已启动的 Docker Compose（包含真实 PG、Redis、ClickHouse 和 MinIO），检查 Gold 的实际写入；在当前交付环境未能运行，详见 `docs/test-report.md`。查看 [部署手册](deployment.md)、[源码审计](source-audit.md)、[字段字典](field-dictionary.md)、[迁移计划](migration-plan.md)、[Runbooks](runbooks.md)。

**红线**：无许可不访问真实 Ozon；挑战、403、身份失效立即暂停相关源。绝不自动破解访问挑战、采集反爬令牌、绕过访问限制或通过多身份/代理重试。真实接口吞吐必须以许可限额、可验证测试和授权监控决定。

## Buyer 12-hour benchmark (V2, offline by default)

The buyer benchmark is a **separate, single-process audit tool** that writes
only to `benchmark_runs` / `benchmark_intervals` / `benchmark_samples` — it does
NOT upsert into products/keywords/data_sources and does NOT rewire the
production pipeline. Run it offline against a redacted fixture:

```bash
python -m collector.benchmark.cli --mode offline --kind inventory \
  --policy config/benchmark/buyer-inventory.example.yaml \
  --fixture samples/benchmark/buyer_inventory_page.json \
  --duration-seconds 60 --out /tmp/bench-offline/
```

Live mode requires explicit `authorized: true` policy + a warmed cookie pool;
with no sessions it fails closed with `requests=0`. See
[`docs/benchmark/buyer-12h-runbook.md`](benchmark/buyer-12h-runbook.md) and the
[readiness report](benchmark/buyer-12h-readiness-report.md).
