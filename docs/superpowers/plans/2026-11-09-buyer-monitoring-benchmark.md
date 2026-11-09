# Buyer 前台采集监控与 12 小时基准测试 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在既有 `ozon-seller-kit` 仓库中，构建可监控、可安全停止、可复核的 Buyer 库存代理值与商品评论 12 小时稳定性测试工具，为以后正式 5 Worker / 100 万条日快照提供**证据**，不提前重建采集框架。

**Architecture:** 先以 Kit 的前台采集代码/字段字典为基准建立源矩阵与离线样本；用单进程、固定授权限额的基准运行器，通过适配器调用纯解析器，记录请求级指标和 15 分钟统计，并使用现有 PG/对象存储与 Prometheus/Grafana。所有真实在线数据源默认禁用，严格受授权/固定预算/熔断门禁控制。以 `ozon-crawler-local` 仅作日志/错误分类参考，不复制它可能错误的限速、库存含义和端点。

**Tech Stack:** Python 3.11+、pytest/pytest-asyncio、SQLAlchemy 2 / Alembic、PostgreSQL（测试使用 SQLite）、Redis（共享限额时）、Prometheus Client、现有 Grafana/MinIO（合法 raw 的可选存储）；复用 `ozon_buyer` 的纯解析函数。

**Spec:** `docs/superpowers/specs/2026-11-09-buyer-monitoring-benchmark-design.md`

## Global Constraints

- 仅在原仓库 `design/v2-buyer-benchmark` 分支实施；V1 已固定于 `archive/pre-v2-2026-11-09`；未经用户审核不删除旧文件、不覆盖 `main`。
- 数据源优先级：**Kit 的实际源码 + 较新 Kit 数据字典 + 用户已核实的授权限额/脱敏 golden**；`ozon-crawler-local` 只读参考，库存、限速、端点冲突时不采用其断言。
- `stock_max` = 页面最大可购数代理，不是真实仓储库存；无观察到的目标 SKU 不应记成库存 0。没有真实库存源验证不得计算真实库存/销量差分。
- 库存请求的基本粒度是**页面上下文 × 观察到的 SKU**；评论按 SKU 获取。不能假定 `/product/{sku}/` 一定能返回列表页 `stock_max`。
- 线上采集须具备每接口的明确授权、许可范围、固定 `max_rps / max_concurrency / max_requests`、数据留存政策与可用告警；任一缺失只能 Mock/offline。
- 不得复用旧 Cookie 静默预热、挑战求解、自动补池、TLS/UA 伪装或轮换代理绕过访问限制；403/429/身份失效/挑战先熔断，不自动换身份，不自动加速。
- 12 小时是**测试持续时间**，不是保证的采集量；本轮只用单个测试进程，5 Worker 规模与 ClickHouse 正式数据模型留后续。
- 原始评价/图片可能涉及用户内容，遵守授权/数据最小化与保留期；运行日志不得含 URL token、Cookie、账号信息、完整响应或个人信息。
- 每项任务遵守 TDD：先失败测试、后最小实现、再运行 tests、最后提交；无环境不冒充已通过真实联调。

## Review Focus

1. **200 空包**：无明确定义的合法 EOF 证据时不得记为成功 → Task 2 `test_ambiguous_200_empty_is_suspect`。
2. **404/403/429/挑战**：不能当空库存、不能继续刷源 → Task 2 `test_access_restriction_blocks_source`，Task 3 `test_live_policy_does_not_auto_recover`。
3. **同 SKU 多页、跨日重复**：能保留真实观测来源/时间，重复任务不重复算成功 → Task 4 `test_inventory_missing_sku_is_unknown`，Task 5 `test_run_interval_unique_and_idempotent`。
4. **意外关闭与监控故障**：会记录部分测试而不是伪造完成 → Task 7 `test_interrupt_produces_stopped_run`。
5. **敏感信息进入日志或报告**：输出仅允许白名单字段 → Task 2 `test_event_never_serializes_secret_fields`，Task 6 `test_report_has_no_raw_personal_data`。

---

## File Map

| 路径 | 责任 |
|---|---|
| `docs/superpowers/evidence/buyer-source-matrix.md` | Kit 与 crawler-local 冲突裁决、合同/证据状态 |
| `samples/benchmark/buyer_inventory_page.json`、`buyer_reviews_widget.json` | 去敏可公开的合成/获准 golden 示例 |
| `collector/benchmark/contracts.py`、`outcomes.py` | 规范记录与响应结果分类 |
| `collector/benchmark/policy.py` | 固定限额、授权门禁与停止策略 |
| `collector/benchmark/adapters.py` | 仅通过注入的 Transport 获取数据、复用 Kit 纯解析 |
| `collector/benchmark/store.py` | Run/15分钟摘要/抽样观测的持久化，避免全量请求写业务主表 |
| `collector/benchmark/metrics.py`、`report.py` | Prometheus 与脱敏 JSON/Markdown 报告 |
| `collector/benchmark/runner.py`、`cli.py` | 单进程 12h 运行和安全退出 |
| `collector/storage/models.py`、`alembic/versions/f92b0c1d873e_buyer_benchmark_runs.py` | 基准测试独立 PG 表 |
| `docs/benchmark/buyer-12h-runbook.md` | 预检、启动、熔断、验收、日容量估算 |
| `tests/test_buyer_*.py` | 分组件与端到端离线测试 |

### Task 1: Lock source-of-truth, page contexts and offline fixtures

**Files:**
- Create: `docs/superpowers/evidence/buyer-source-matrix.md`
- Create: `samples/benchmark/buyer_inventory_page.json`, `samples/benchmark/buyer_reviews_widget.json`
- Create: `tests/test_buyer_contract.py`
- Create: `collector/benchmark/__init__.py`, `collector/benchmark/contracts.py`

**Interfaces:**
- Produces `InventoryObservation(sku, page_path, source, region, observed_at, stock_proxy_value, raw_field_path)` and `ReviewObservation(sku, review_id, score, observed_at, source)` (no personal identifiers required).
- Produces `validate_inventory_record(data: dict) -> InventoryObservation` and `validate_review_record(data: dict) -> ReviewObservation`; missing fields stay `None`.

- [ ] **Step 1: Write failing contract tests.** `tests/test_buyer_contract.py` contains `test_stock_max_is_proxy_not_physical` (input `maxItems=2000`, output `stock_proxy_value==2000`, `physical_stock is absent`) and `test_unknown_stock_stays_null` (missing `maxItems` → `stock_proxy_value is None`).
- [ ] **Step 2: Run** `pytest -q tests/test_buyer_contract.py` and confirm tests FAIL (missing module/contracts).
- [ ] **Step 3: Create** `contracts.py` dataclasses and normalization validators. Document **Kit** path/func (`ozon_buyer/collector.py:extract_skus_from_page`, `ozon_buyer/http.py:parse_tile`, `ozon_buyer/detail.py:parse_reviews`), actual query/page contexts and ambiguous alternatives; write two synthetic sanitized fixtures matching known Kit widget structure. List `ozon-crawler-local/docs/api/C01-buyer-entrypoint-widget.md` as secondary reference only. Link source commit and fixture SHA256. Explicitly disallow assuming a SKU-only PDP contains listing-page stock.
- [ ] **Step 4: Run** `pytest -q tests/test_buyer_contract.py` and confirm PASS.
- [ ] **Step 5: Commit** `git add collector/benchmark/__init__.py collector/benchmark/contracts.py tests/test_buyer_contract.py samples/benchmark docs/superpowers/evidence && git commit -m "test: lock buyer inventory and review data contracts"`.

### Task 2: Classify outcomes and sanitise event logs

**Files:**
- Create: `collector/benchmark/outcomes.py`, `collector/benchmark/events.py`
- Create: `tests/test_buyer_outcomes.py`

**Interfaces:**
- Consumes `HTTP status`, `response content-type`, `parsed envelope`, `expected widget kind` (not authenticated headers).
- Produces `classify_buyer_response(status_code: int, content_type: str, body: object, kind: str) -> Outcome`, where Outcome is `ok | empty_valid | empty_suspect | blocked | transient_error | invalid`.
- Produces `safe_event_dict(*, run_id: str, source_id: str, elapsed_ms: float, outcome: str, status_code: int | None, records: int) -> dict` (strict field whitelist).

- [ ] **Step 1: Write failing tests** for 200+valid tile, 200+valid explicit EOF, 200+missing widget, 403/429/redirect/challenge, invalid JSON, 5xx; assert ambiguous empty = `empty_suspect` and access-restricted = `blocked`. Test a response containing `cookie`, `authorization`, token-bearing URL and review author does not appear in event serialization.
- [ ] **Step 2: Run** `pytest -q tests/test_buyer_outcomes.py` to observe FAIL.
- [ ] **Step 3: Implement** classification using existing `collector/errors.py` safety semantics; only accept `empty_valid` with explicit terminal evidence from Kit fixtures; all ambiguous empties fail closed. JSONL event writer only serializes `safe_event_dict` (no raw exception text).
- [ ] **Step 4: Run** `pytest -q tests/test_buyer_outcomes.py` to PASS.
- [ ] **Step 5: Commit** `git add collector/benchmark/outcomes.py collector/benchmark/events.py tests/test_buyer_outcomes.py && git commit -m "feat: classify and sanitise buyer benchmark events"`.

### Task 3: Define fixed policy and authorised transport boundary

**Files:**
- Create: `collector/benchmark/policy.py`
- Create: `config/benchmark/buyer-inventory.example.yaml`, `config/benchmark/buyer-reviews.example.yaml`
- Create: `tests/test_buyer_policy.py`

**Interfaces:**
- Produces `load_benchmark_policy(path: str, mode: str) -> BenchmarkPolicy` with `source_id`, `kind`, `allowed_endpoint`, `max_rps`, `max_concurrency`, `max_requests`, `duration_seconds`, `license_ref`, `retention`, `mode`.
- Produces `require_live_authorization(policy: BenchmarkPolicy) -> None`; when mode=live and explicit verified policy fields are absent, raises `PolicyViolation`.

- [ ] **Step 1: Write failing tests**: no live budget/no permission/unapproved endpoint is rejected; offline works without network; 403/429 causes permanent source stop for that run; no retry or automatic rate increase; policy is separate for inventory and reviews.
- [ ] **Step 2: Run** `pytest -q tests/test_buyer_policy.py` to FAIL.
- [ ] **Step 3: Implement** validation and typed policy. YAML examples contain **no guessed numerical online limits**; online values must be copied from Kit evidence + verified licensed policy, with `authorized: false` by default. Shared Redis permit (`collector/rate_limit/distributed.py`) used if more than one process ever runs; this first test has one process and must not run multi-process accidentally.
- [ ] **Step 4: Run** `pytest -q tests/test_buyer_policy.py` to PASS.
- [ ] **Step 5: Commit** `git add collector/benchmark/policy.py config/benchmark tests/test_buyer_policy.py && git commit -m "feat: gate buyer benchmarks by explicit source policy"`.

### Task 4: Build the isolated inventory/review benchmark adapters

**Files:**
- Create: `collector/benchmark/adapters.py`
- Create: `tests/test_buyer_adapters.py`

**Interfaces:**
- Consumes `BuyerTransport.fetch_page(page_path: str) -> ResponseEnvelope` (injected implementation; test fake only by default), plus Kit pure parsers.
- Produces `collect_inventory_page(transport: BuyerTransport, page_path: str, wanted_skus: set[str], observed_at: datetime) -> list[InventoryObservation]`.
- Produces `collect_review_page(transport: BuyerTransport, sku: str, page_path: str, observed_at: datetime) -> list[ReviewObservation]`.

- [ ] **Step 1: Write failing tests**: 8 inventory tiles contains only requested 3 SKUs → 3 observations with page provenance; absent desired SKU → no invented zero; valid reviews widget maps 2 records; wrong/missing widget → `empty_suspect`, not empty success; no network is attempted by fixtures.
- [ ] **Step 2: Run** `pytest -q tests/test_buyer_adapters.py` and confirm FAIL.
- [ ] **Step 3: Implement** adapters wrapping Kit `extract_skus_from_page` / `parse_reviews` without calling `BuyerClient.ensure_creds`, `PoolClient`, `cdp_warmup` or legacy retry paths. Keep the Transport boundary explicit; a live implementation is allowed **only if** approved source matrix + authorization policy and no anti-access-control bypass. Do not silently substitute endpoint from crawler-local if Kit fails.
- [ ] **Step 4: Run** `pytest -q tests/test_buyer_adapters.py` to PASS.
- [ ] **Step 5: Commit** `git add collector/benchmark/adapters.py tests/test_buyer_adapters.py && git commit -m "feat: isolate buyer inventory and review sample adapters"`.

### Task 5: Persist experiment runs, intervals and limited samples

**Files:**
- Modify: `collector/storage/models.py`
- Create: `alembic/versions/f92b0c1d873e_buyer_benchmark_runs.py` (`down_revision='78a91cdf1b16'` on current main; verify head again before applying)
- Create: `collector/benchmark/store.py`
- Create: `tests/test_buyer_benchmark_store.py`

**Interfaces:**
- Defines `BenchmarkRun(run_id, kind, source_id, mode, started_at, stopped_at, status, stop_reason, policy_hash)`.
- Defines `BenchmarkInterval(run_id, window_start, requests, records, ok, empty_valid, empty_suspect, blocked, error, latency_p50_ms, latency_p95_ms, latency_p99_ms, bytes_received)`, unique `(run_id, window_start)`.
- Defines `BenchmarkSample(run_id, kind, source_id, sku, page_path, observed_at, value, raw_sha256)` with strict sample quota; no raw reviews/author fields in PG.
- Produces `BenchmarkStore.start_run()`, `upsert_interval()`, `save_sample()`, `finish_run()`.

- [ ] **Step 1: Write failing tests** for two windows, repeated interval write (one row), null stock value preserved, cross-date snapshots kept distinct, failed persistence preventing completed status, no secret fields.
- [ ] **Step 2: Run** `pytest -q tests/test_buyer_benchmark_store.py` → FAIL.
- [ ] **Step 3: Implement** models, migration and store. Write raw response only to approved MinIO location with hash/retention when explicitly permitted; otherwise store only safe digests/metrics. Reuse existing PG instead of new database. No product/Keyword master-upserts during benchmark.
- [ ] **Step 4: Run** `pytest -q tests/test_buyer_benchmark_store.py` and `DATABASE_URL=sqlite:////tmp/ozon-buyer-bench-migration.db alembic upgrade head` → PASS / latest revision `f92b0c1d873e`; production PG migration requires separate check.
- [ ] **Step 5: Commit** `git add collector/storage/models.py alembic/versions/f92b0c1d873e_buyer_benchmark_runs.py collector/benchmark/store.py tests/test_buyer_benchmark_store.py && git commit -m "feat: persist benchmark runs and intervals"`.

### Task 6: Metrics, 15-minute snapshots and output report

**Files:**
- Create: `collector/benchmark/metrics.py`, `collector/benchmark/report.py`
- Create: `tests/test_buyer_benchmark_report.py`

**Interfaces:**
- Produces `BenchmarkMetrics.record(outcome: Outcome, duration_seconds: float, records: int, bytes_received: int) -> None` with bounded `source/kind/outcome` labels; never use SKU or URL as Prometheus label.
- Produces `build_benchmark_report(run: BenchmarkRun, intervals: list[BenchmarkInterval]) -> dict` and `render_markdown_report(report: dict) -> str`.

- [ ] **Step 1: Write failing tests** with 15-minute windows verifying request rate, effective rows/h, failure buckets, P50/P95/P99 based on raw durations and duration-weighted capacity, complete vs stopped status; ensure report has no raw user comments or tokens.
- [ ] **Step 2: Run** `pytest -q tests/test_buyer_benchmark_report.py` → FAIL.
- [ ] **Step 3: Implement** monotonic timers / UTC boundaries, bounded cardinality counters/histograms, interval flush every 900 seconds, minimal JSON + Markdown reports. Report original license/policy version, 12h actual runtime, p95 trend, error rates, source-specific sustainable throughput and **uncertainty**; never claim 5× scaling or “physical stock accuracy”.
- [ ] **Step 4: Run** `pytest -q tests/test_buyer_benchmark_report.py` → PASS.
- [ ] **Step 5: Commit** `git add collector/benchmark/metrics.py collector/benchmark/report.py tests/test_buyer_benchmark_report.py && git commit -m "feat: report 15-minute buyer benchmark intervals"`.

### Task 7: 12-hour runner, safe stop and executable CLI

**Files:**
- Create: `collector/benchmark/runner.py`, `collector/benchmark/cli.py`
- Create: `tests/test_buyer_benchmark_runner.py`

**Interfaces:**
- Consumes `BenchmarkPolicy`, injected `BuyerTransport`, `BenchmarkStore`, `BenchmarkMetrics`, `clock`.
- Produces `async run_experiment(policy: BenchmarkPolicy, adapter, store, metrics, *, clock) -> BenchmarkSummary`; **no live transport is auto-created**.
- CLI: `python -m collector.benchmark.cli --mode offline --kind inventory --policy config/benchmark/buyer-inventory.example.yaml --fixture samples/benchmark/buyer_inventory_page.json --duration-seconds 60`; permitted live invocation must pass an explicit approved connection config and no default live mode.

- [ ] **Step 1: Write failing tests** for 1-minute fake-clock offline run, fixed 900s interval flush, manual stop/SIGTERM, 12-hour time boundary, no successful completion on write failure, no re-entry when blocked, exact budget enforcement.
- [ ] **Step 2: Run** `pytest -q tests/test_buyer_benchmark_runner.py` → FAIL.
- [ ] **Step 3: Implement** single-process bounded async loop; always check policy, source state and monotonic deadline **before** acquiring next request; backpressure when sink is slow. Stop with `completed` only at natural time limit with all metrics flushed; otherwise `stopped/blocked/failed`, with partial report and checkpoint. Use no endless auto retries.
- [ ] **Step 4: Run** `pytest -q tests/test_buyer_benchmark_runner.py` → PASS.
- [ ] **Step 5: Commit** `git add collector/benchmark/runner.py collector/benchmark/cli.py tests/test_buyer_benchmark_runner.py && git commit -m "feat: add bounded 12-hour benchmark runner"`.

### Task 8: Local smoke test, runbook and release gate

**Files:**
- Create: `tests/test_buyer_benchmark_e2e.py`
- Create: `docs/benchmark/buyer-12h-runbook.md`
- Modify: `docs/collector-runtime.md` (only link/usage; not rewire production)
- Optional (only if proven required): `observability/prometheus/prometheus.yml` (benchmark scrape target must not silently create failing production alerts).

**Interfaces:**
- Consumes previously defined CLI, fixtures, policy, store/report, and on-demand metrics HTTP endpoint.
- Produces a reproducible offline smoke, readiness checklist and handoff for a separately approved live 12-hour run.

- [ ] **Step 1: Write failing end-to-end test** `test_offline_buyer_benchmark_e2e_writes_run_intervals_report`: fixtures → Adapter → Runner → Store → Report; assert `mode=offline`, no network, deterministic summary, no real Cookie/PII.
- [ ] **Step 2: Run** `pytest -q tests/test_buyer_benchmark_e2e.py` → FAIL.
- [ ] **Step 3: Implement** runbook with (a) Kit/Crawler source matrix and endpoint validation, (b) per-interface permitted budget, (c) offline-first preflight, (d) approved single-run 12h schedule, (e) 15min summary/Prometheus + alert receiver test, (f) pause/abort runbooks, (g) acceptance and retention policy, (h) output for Worker sizing. Document that no live experiment starts absent explicit credentials/authorization/field verification.
- [ ] **Step 4: Run** `pytest -q tests/test_buyer_*.py && pytest -q`; run offline smoke CLI in short duration; run PG/Redis/MinIO + Alertmanager integration in an approved environment separately, *not* claim success from mocks.
- [ ] **Step 5: Commit** `git add tests/test_buyer_benchmark_e2e.py docs/benchmark/buyer-12h-runbook.md docs/collector-runtime.md && git commit -m "docs: validate and hand off buyer 12-hour benchmark"`.

## Preflight Gate for Actual 12h Online Run

- [ ] 用户/管理员提供并批准**库存源**授权、确切页型/endpoint、来源证据、每分钟和最大并发上限、预计请求总数、合法的账号/凭证使用方式以及数据留存范围。
- [ ] 同样为**评论源**独立提供上述政策；不共享或继承库存源预算。
- [ ] 基于 Kit 正确版本的人工审阅通过，确认源矩阵中无未经裁决的关键字段/端点冲突；`ozon-crawler-local` 的任何限速、库存结论不进入批准的在线参数。
- [ ] 运行时日志脱敏、PG/MinIO 真实写入、告警发送链路、CPU/内存/磁盘空间和人工急停已验证。
- [ ] 先跑 Mock / offline / 低频短跑；若实际授权访问被挑战或拒绝，立即停源并标 `blocked`，不求“12h 跑满”。
- [ ] 12h 结束后核对事件总数、15min interval 总数（正常 48 个完整窗口）、错误分布、抽样响应 hash 与数据库 idempotency；整理吞吐区间，不自动上调速率。

## Plan Self-Review / Execution Handoff

- **Spec coverage**：源优先级 (T1)、错误/熔断 (T2/3)、两类采集 (T4)、数据与留存 (T5)、监控和报告 (T6)、12h 执行/终止 (T7)、可重复验收 (T8)。
- **Boundary**：不触碰后台 P6/P7/P8，不实现正式分布式 Worker，不假定库存准确，不默认线上请求。
- **Execution choice**：建议 **Subagent-driven**（每个任务单独复核；源可信度/权限/数据质量失败成本高）。用户审阅本 Plan 后再选执行方式，随后按 Superpowers skill 实施。
