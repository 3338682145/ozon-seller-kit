# Buyer 12-Hour Benchmark Runbook

Single-process, auditable, safely-stoppable stability test for Ozon buyer
inventory proxy values and review volume. This is an **evidence-gathering
run**, not a production collector. It does NOT scale to 5 Workers, does NOT
claim physical stock accuracy, and does NOT start without explicit approval.

## 1. Source matrix and endpoint validation

- Parsers are reused from `ozon_buyer/collector.py:extract_skus_from_page` and
  `ozon_buyer/detail.py:parse_reviews`; V2 only normalises their output.
- Inventory observations carry TWO parallel fields (spec 10.3):
  `stock_proxy_max_items` (tile `maxItems`, a per-purchase quantity cap — NOT
  physical stock) and `stock_text_remaining` (the Russian "N ед осталось"
  copy). At `maxItems == 2000` both are kept and `is_capped=true`.
- Reviews carry `review_id` (nullable, never synthesised from author+body) and
  `score` (must be 1..5; out-of-range isolated as invalid).
- `ozon-crawler-local` is reference-only; its rate limits and stock conclusions
  are NOT adopted.

## 2. Independent source budgets

Inventory and reviews have independent policies in
`config/benchmark/buyer-inventory.example.yaml` and
`buyer-reviews.example.yaml`. They do not share or inherit budgets.

When numeric limits are omitted the runner falls back to conservative starting
values and marks them `estimated`:

| parameter | conservative start | status |
|---|---|---|
| max_concurrency | 20 | estimated |
| cookie_max_uses | 30 | estimated |
| max_rps | 4.6 pages/s | estimated |
| burst | 8 | estimated |

These are re-tuned ONLY by an approved 12h run; never auto-raised on errors.

## 3. Offline-first preflight (no network)

```bash
python -m pip install -e '.[test]'
pytest -q tests/test_buyer_*.py
python -m collector.benchmark.cli \
  --mode offline --kind inventory \
  --policy config/benchmark/buyer-inventory.example.yaml \
  --fixture samples/benchmark/buyer_inventory_page.json \
  --duration-seconds 60 --out /tmp/bench-offline/
```

This writes `events/events-*.jsonl`, `benchmark.sqlite`, `report.json` and
`report.md` under `--out`. It opens zero sockets.

## 4. Live run scheduling (requires separate approval)

A live 12h run requires ALL of:

1. Cookie supply gate passes 20 consecutive `mint()` calls (each ≤5 s, no
   cookie plaintext in logs) — currently **BLOCKED** in this sandbox because
   `abt_data` is permanently 485 (< 580) and challenge static resources return
   403; see `docs/benchmark/evidence/t0-cookie-supply-smoke.md`.
2. Source budgets filled from Kit evidence + a verified licensed policy file
   with `authorized: true`.
3. Alertmanager P0/P1 delivery to a real email/webhook recipient verified.
4. Human on-call for the one-key stop (`SIGTERM`).

Until all four are green, `--mode live` fails closed with `requests=0` and
`status=blocked`.

## 5. Interval summaries, Prometheus and alerts

- Every 900 s a `BenchmarkInterval` row is upserted (idempotent on
  `(run_id, window_start)`).
- A local Prometheus endpoint (optional, `metrics.serve(port)`) exposes only
  bounded labels `source/kind/outcome` — never SKU or URL.
- Alertmanager is configured `local-only`; external delivery must be wired and
  tested before a live run.

## 6. Pause / abort

- `SIGTERM` (or Ctrl-C) sets a stop event; the runner finishes the in-flight
  attempt, flushes the partial window, and exits `status=stopped`. It never
  reports `completed` on a manual stop.
- Three consecutive tickets returning 401/403/429/challenge stops the source
  (`status=blocked`). A single ticket's failure only marks that ticket dead.
- Event-log or DB write failure stops new requests (`status=failed`).

## 7. Acceptance and retention

- Reconciliation: sum of interval `audit_event_count` == terminal event log
  count. The report's `reconciliation.matched` must be `true`.
- Retention: request-event JSONL 30 days, interval summaries 180 days,
  samples 7 days. Raw responses are NOT stored unless explicitly approved and
  encrypted in object storage with expiry.
- Logs must contain no cookie plaintext, URL query strings, review author or
  comment body.

## 8. Outputs for worker sizing

The report is **single-process observed throughput only**. It must NOT be
linearly extrapolated to 5 Workers. The report carries an explicit uncertainty
note: "Do NOT linearly extrapolate to 5 Workers." Shared-Redis permits are a
separate multi-process integration test.

## 9. Request-event reconciliation and field validity

Every attempt produces exactly one `RequestAuditEvent` (whitelist keys only).
Per-batch quality counters (`valid_count` / `invalid_count` / `unknown_count`)
are persisted on each interval; 200 empty widgets are `empty_suspect`, never
silent success.

## 10. Followed redirects

3xx search-page redirects are normal ranking jitter. The live HTTP transport
must use `allow_redirects=True` and classify the FINAL page; if a redirect is
recorded it carries `reason_code=redirect_followed` and never lands in the
`invalid`/`error` bucket.
