# Buyer Benchmark Report — 0613c3207d20

- mode: `offline`  status: **stopped**  kind: `inventory`  source: `buyer-inventory`
- window: 2026-11-09T15:37:00Z → 2026-11-09T15:37:00Z (0.866s)
- policy_version: `v1`  schema_version: `buyer-v2-1`

## Totals
- requests: 11  records: 33  bytes: 18898
- ok: 11  empty_valid: 0  empty_suspect: 0  blocked: 0  error: 0
- valid: 33  invalid: 0  unknown: 0

## Throughput (single process, observed)
- observed_rps: 12.6985  policy_rps cap: 4.6  utilization: 2.7605

## Reconciliation
- interval audit_event_count sum: 11
- terminal event log count: 11  matched: **True**

## Windows
- 2026-11-09T15:37:00Z: requests=11 ok=11 error=0 p95_ms=0.013

## Uncertainty

- Single-process observed throughput. Do NOT linearly extrapolate to 5 Workers.
- stock_proxy_max_items is a per-purchase quantity cap, not physical stock.
- Conservative starting limits (20 concurrency / 30 uses-per-cookie / 4.6 rps) are estimated until a 12h approved run re-tunes them.
