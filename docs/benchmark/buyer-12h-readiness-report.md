# Buyer 12-Hour Benchmark · Readiness Report

Branch: `design/v2-buyer-benchmark` · T5–T8 commits:
`d0819ef` (persist runs/intervals) · `a812fd7` (15-min report) ·
`c7bdec4` (bounded runner) · `55dce42` (e2e + runbook handoff).

Baseline T0–T4 (`8575b0e`..`c4644c7`) untouched. Full suite: **116 passed**.

## Three-column evidence: observed / estimated / unknown

| Metric | observed (measured here) | estimated (conservative start) | unknown (not tested) |
|---|---|---|---|
| Requests per offline run | **11** (stopped by 4.6 rps budget after burst=8 + refill) | — | sustained 12h request count |
| Observed rps (single process) | **12.70** over ~0.87 s wall (burst-driven, not sustained) | 4.6 pages/s cap | sustained rps over 15-min window |
| Peak concurrency | capped at policy `max_concurrency` (default 20) by the limiter | 20 | real peak under load |
| Records per request | **3** (3 wanted SKUs on the fixture tile grid) | — | real SKU yield on live search |
| Valid / invalid / unknown records | **33 / 0 / 0** on the fixture | — | field-drift rates on live |
| P50 / P95 / P99 latency | ms-level on local fixture (see `report.json`) | — | live e2e latency incl. TLS+challenge |
| Cookie uses per ticket | — | **30** (Kit starting value) | real lifetime before 403 |
| Burst / rps / concurrency | — | **8 / 4.6 / 20** | verified licensed limits |
| Event/interval reconciliation | **11 events == 11 audit_event_count, matched=true** | — | reconciliation over 48 windows |
| Live cookie mint success | **0** (T0 blocked: abt_data=485 < 580) | 20/20 required | whether a live mint ever passes |
| Alertmanager P0/P1 delivery | **not configured** (local-only receiver) | — | real email/webhook end-to-end |
| 5-Worker throughput | — | — | **never extrapolated; unknown by design** |
| Physical stock accuracy | — | — | unknown; `maxItems` is a proxy only |

## A1–A6 gate

| Gate | Result | Evidence |
|---|---|---|
| **A1** Offline suite green | **PASS** | `pytest -q` → 116 passed (41 baseline + 75 buyer-benchmark). Re-run: `/home/user/Doubao/chats/38452651909603330/venv-ozon-kit/bin/python -m pytest` |
| **A2** Log whitelist / no PII leak | **PASS** | `grep -riE 'abt_data=|cookie:|session=|authorization:' events/ report.md` → 0 hits. Whitelist 19 keys per spec §10.1; `raw_sha256` dropped by default. |
| **A3** Inventory three-state (0/NULL/capped) + 200-empty=empty_suspect + 403=blocked + 3xx-not-rejected | **PASS** | Locked in T1/T4/T6 tests: `test_capped_max_items_keeps_text_value`, `test_unknown_stock_stays_null`, `test_followed_redirect_lands_in_ok_not_error`. Followed 302→200 lands in `ok`, never in error bucket. |
| **A4** Cookie supply 20-mint smoke | **BLOCKED** | T0 environment-level: `abt_data` permanently 485 (< 580 threshold), headless vs headful+Xvfb identical, challenge static resources `st-20.ozonstatic.cn` 403. Thresholds 580/2/`abt_att=1` NOT lowered. Evidence: `docs/benchmark/evidence/t0-cookie-supply-smoke.md`. No fake mint. |
| **A5** 60s real online sprint | **BLOCKED** | Consequence of A4. Live CLI with `authorized: true` but no cookie pool: `requests=0`, `status=blocked`, `stop_reason=live_requires_cookie_supply`, 0 events on disk. Evidence: `docs/benchmark/evidence/live-fail-closed/`. |
| **A6** Alertmanager P0/P1 delivery | **BLOCKED** | `observability/alertmanager/config.yml` route receiver is `local-only`; no email/webhook recipient. Missing: a real recipient + a P0/P1实发 test. Not faked. |

## Offline 60s sprint (real numbers)

Command:
```bash
python -m collector.benchmark.cli --mode offline --kind inventory \
  --policy config/benchmark/buyer-inventory.example.yaml \
  --fixture samples/benchmark/buyer_inventory_page.json \
  --duration-seconds 60 --out docs/benchmark/evidence/offline-60s \
  --wanted-skus 111222333,444555666,777888999 --max-attempts 300
```

Result:
- **requests: 11** (the conservative 4.6 rps budget stopped it after burst=8 + ~3 refill; this is budget enforcement, not a crash)
- **observed rps: 12.70** (burst-driven over ~0.87 s; not a sustained 15-min rate)
- **peak concurrency**: bounded by `max_concurrency=20` in the limiter
- **events total: 11** (one terminal event per attempt)
- **interval total: 1** window, `audit_event_count=11`
- **reconciliation: matched=true** (11 interval == 11 event-log lines)
- **records: 33** (3 SKUs × 11 attempts), valid=33, invalid=0, unknown=0
- Artifacts (absolute paths):
  - `docs/benchmark/evidence/offline-60s/events/events-2026-11-09.jsonl`
  - `docs/benchmark/evidence/offline-60s/benchmark.sqlite` (interval + sample tables)
  - `docs/benchmark/evidence/offline-60s/report.json`
  - `docs/benchmark/evidence/offline-60s/report.md`

## Live fail-closed evidence

Command (with `authorized: true` policy but no cookie pool wired):
```bash
python -m collector.benchmark.cli --mode live --policy /tmp/authorized-policy.yaml \
  --duration-seconds 60 --out /tmp/bench-live2
```
- exit=1, `status=blocked`, `stop_reason=live_requires_cookie_supply`
- **requests=0**, **0 lines in events JSONL**, interval row `(requests=0, audit_event_count=0)`
- A policy with `authorized: false` rejects even earlier (exit=2, no output files).
- One-key stop: graceful SIGTERM path is unit-tested
  (`tests/test_buyer_benchmark_runner.py::test_manual_stop_produces_stopped_not_completed`);
  a hard kill leaves the run row `running` (honest crash state, never a fake `completed`).

## Alembic migration evidence

```
DATABASE_URL=sqlite:////tmp/ozon-buyer-bench-migration.db alembic upgrade head
# ...
# Running upgrade 78a91cdf1b16 -> f92b0c1d873e, buyer benchmark runs, intervals and samples.
# f92b0c1d873e (head)
```
Down-revision chain: `c539a5e4bb5c → 5f4922bf2679 → 72d0e451ab02 → 78a91cdf1b16 → f92b0c1d873e`.

## Explicitly NOT tested (no mock-as-real)

- **Live egress to ozon.ru**: never attempted; T0 blocked by environment.
- **Real cookie mint / challenge pass**: not possible in this sandbox.
- **Sustained 15-min / 12-h throughput**: offline fixture is sub-second; the
  12h run requires separate human approval and is NOT started here.
- **5-Worker / shared-Redis permit**: out of scope; single-process only.
- **Real PostgreSQL / MinIO writes**: tests use SQLite; PG migration is
  forward-compatible but not exercised against a live PG.
- **Prometheus / Grafana dashboards**: local endpoint exists but no scrape
  target wired (would create failing production alerts otherwise).
- **Alertmanager P0/P1实发**: blocked (no recipient).
- **Real review body / PII handling on live widgets**: fixtures are
  `CONSTRUCTED` (provenance field); the review parser is exercised on the
  redacted golden only.

## To unblock a live 12h run

1. Fix the cookie supply gate in an environment where `abt_data` reaches ≥580
   with two stable polls and `abt_att=1` in URL (currently blocked).
2. Fill source budgets from Kit evidence + a licensed policy (`authorized: true`).
3. Wire a real Alertmanager email/webhook recipient and verify P0/P1 delivery.
4. Re-run the offline 60s sprint, then a human-approved 60s live sprint, then
   only then the 12h run.
