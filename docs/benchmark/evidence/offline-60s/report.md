# Buyer Benchmark Report — a1f8e40ed070

- mode: `offline`  status: **completed**  kind: `inventory`  source: `buyer-inventory`
- window: 2026-11-09T15:50:05Z → 2026-11-09T15:51:05Z (60.097s)
- policy_version: `v1`  schema_version: `buyer-v2-1`

## Totals
- requests: 284  records: 852  bytes: 487912
- ok: 284  empty_valid: 0  empty_suspect: 0  blocked: 0  error: 0
- valid: 852  invalid: 0  unknown: 0

## Throughput (single process, observed)
- observed_rps: 4.7257  policy_rps cap: 4.6  utilization: 1.0273

## Reconciliation
- interval audit_event_count sum: 284
- terminal event log count: 284  matched: **True**

## Windows
- 2026-11-09T15:50:05Z: requests=284 ok=284 error=0 p95_ms=0.016

## Uncertainty

- Single-process observed throughput. Do NOT linearly extrapolate to 5 Workers.
- stock_proxy_max_items is a per-purchase quantity cap, not physical stock.
- Conservative starting limits (20 concurrency / 30 uses-per-cookie / 4.6 rps) are estimated until a 12h approved run re-tunes them.
