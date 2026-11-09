# Buyer Benchmark Report — 41a105ed7cae

- mode: `live`  status: **blocked**  kind: `inventory`  source: `buyer-inventory`
- window: 2026-11-09T15:38:01Z → 2026-11-09T15:38:01Z (0.01s)
- policy_version: `v1`  schema_version: `buyer-v2-1`

## Totals
- requests: 0  records: 0  bytes: 0
- ok: 0  empty_valid: 0  empty_suspect: 0  blocked: 0  error: 0
- valid: 0  invalid: 0  unknown: 0

## Throughput (single process, observed)
- observed_rps: 0.0  policy_rps cap: 4.6  utilization: 0.0

## Reconciliation
- interval audit_event_count sum: 0
- terminal event log count: 0  matched: **True**

## Windows
- 2026-11-09T15:38:01Z: requests=0 ok=0 error=0 p95_ms=None

## Uncertainty

- Single-process observed throughput. Do NOT linearly extrapolate to 5 Workers.
- stock_proxy_max_items is a per-purchase quantity cap, not physical stock.
- Conservative starting limits (20 concurrency / 30 uses-per-cookie / 4.6 rps) are estimated until a 12h approved run re-tunes them.
