# Buyer 前台采集监控与 12 小时基准测试 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在既有 `ozon-seller-kit` 仓库中，构建可监控、可安全停止、可复核的 Buyer 库存代理值与商品评论 12 小时稳定性测试工具，为以后正式 5 Worker / 100 万条日快照提供**证据**，不提前重建采集框架。

**Architecture:** 先以 Kit 的前台采集代码/字段字典为基准建立源矩阵与离线样本；再建 Cookie 供给门（Task 0，预热门 + 池），它是所有在线任务的前置；然后用单进程基准运行器，通过适配器调用纯解析器，记录请求级指标和 15 分钟统计，并使用现有 PG/对象存储与 Prometheus/Grafana。在线模式以「供给门可跑通 + 源级预算已填」为条件，预算缺省时按保守起步值运行而非阻断。以 `ozon-crawler-local` 仅作日志/错误分类参考，不复制它可能错误的限速、库存含义和端点。

**Tech Stack:** Python 3.11+、pytest/pytest-asyncio、SQLAlchemy 2 / Alembic、PostgreSQL（测试使用 SQLite）、Redis（共享限额时）、Prometheus Client、现有 Grafana/MinIO（合法 raw 的可选存储）；复用 `ozon_buyer` 的纯解析函数。

**Spec:** `docs/superpowers/specs/2026-11-09-buyer-monitoring-benchmark-design.md`

## Global Constraints

- 仅在原仓库 `design/v2-buyer-benchmark` 分支实施；V1 已固定于 `archive/pre-v2-2026-11-09`；未经用户审核不删除旧文件、不覆盖 `main`。
- 数据源优先级：**Kit 的实际源码 + 较新 Kit 数据字典 + 用户已核实的授权限额/脱敏 golden**；`ozon-crawler-local` 只读参考，库存、限速、端点冲突时不采用其断言。
- `stock_max` = 页面最大可购数代理，不是真实仓储库存；无观察到的目标 SKU 不应记成库存 0。没有真实库存源验证不得计算真实库存/销量差分。
- 库存请求的基本粒度是**页面上下文 × 观察到的 SKU**；评论按 SKU 获取。不能假定 `/product/{sku}/` 一定能返回列表页 `stock_max`。
- 线上采集以实测可通的 Cookie 供给方案（Task 0）为前提；`max_rps / max_concurrency / max_requests` 由预检填入源级预算，未核实时先按保守起步值（单 cookie 约 30 次、单进程 20 并发），不因缺省而阻断实验。
- Cookie 供给是硬前置：**允许** CDP 无头预热获取挑战令牌、池内按失效标记轮换、过期后重新预热；**禁止**代理或出口 IP 轮换（用户已多次明确否决）、伪造跨账号身份、对同一失效身份无限重试。403/429/挑战先对该票据熔断并标 dead，再从池里取下一枚——换的是同一身份池里的过期票据，不是造新身份。详见 spec 4.4。
- 12 小时是**测试持续时间**，不是保证的采集量；本轮只用单个测试进程，5 Worker 规模与 ClickHouse 正式数据模型留后续。
- 原始评价/图片可能涉及用户内容，遵守授权/数据最小化与保留期；运行日志不得含 URL token、Cookie、账号信息、完整响应或个人信息。
- 每项任务遵守 TDD：先失败测试、后最小实现、再运行 tests、最后提交；无环境不冒充已通过真实联调。
- **日志、限速、字段验证为阻断项**：每个请求均有可追溯的唯一终态事件；各接口都有全局固定限额；字段漂移和可疑空包不得计入有效采集。日志、数据或监控不能持久化时必须停止发请求。
- **留存建议**：脱敏 JSONL 30 天、15 分钟汇总 180 天、最小匿名样本 7 天；由更严格的授权政策覆盖。原始响应默认不存。

## Review Focus

1. **200 空包**：无明确定义的合法 EOF 证据时不得记为成功 → Task 2 `test_ambiguous_200_empty_is_suspect`。
2. **404/403/429/挑战**：不能当空库存、不能继续刷源 → Task 2 `test_access_restriction_blocks_source`，Task 3 `test_live_policy_does_not_auto_recover`。
3. **同 SKU 多页、跨日重复**：能保留真实观测来源/时间，重复任务不重复算成功 → Task 4 `test_inventory_missing_sku_is_unknown`，Task 5 `test_run_interval_unique_and_idempotent`。
4. **意外关闭与监控故障**：会记录部分测试而不是伪造完成 → Task 7 `test_interrupt_produces_stopped_run`。
5. **敏感信息进入日志或报告**：输出仅允许白名单字段 → Task 2 `test_event_never_serializes_secret_fields`，Task 6 `test_report_has_no_raw_personal_data`。

---

## Runtime Contract：最小可验收要求（T1–T8）

**持久化日志（T2/T5）**：每次 HTTP 调用（成功、失败、超时、限流拒绝、取消）都要有单独 `RequestAuditEvent`，终态唯一键 `run_id+request_id+attempt`。仅存 `ts_utc,run_id,batch_id,request_id,source_id,endpoint_id,attempt,status_code,outcome,duration_ms,permit_wait_ms,response_bytes,observed_records,accepted_records,schema_version,validation_error_codes,write_status,reason_code`；许可后可选 `raw_sha256`。不能写 Cookie、token、URL 查询串、用户评论正文/作者、异常原文。JSONL 按日期或大小轮转，保留期结束自动清理；失败停源。15 分钟 `BenchmarkInterval` 与请求事件总数必须对账。

**独立限速（T3/T7）**：库存、评论各有经授权核实的 `max_rps,burst,max_concurrency,min_interval_seconds,max_requests,max_requests_per_day,allowed_endpoint,license_ref,policy_version`。每次调用前原子领取许可，重试也计入限额。当前只有单测试进程；未来 5 Worker 必须共享同一源级限额，不可按 Worker 倍增。无许可证据和已审批数值时，online 模式 fail-closed。

**字段契约（T1/T4/T6）**：库存 `sku` 为 TEXT、采集时刻为 UTC、来源页型必填；`stock_max` 是 nullable int 代理量，0 与 NULL 不可混淆，负数/非数字无效，2000 上限要标 `is_capped` 不能称为物理库存。评论 score 存在时须在 1–5，review_id 可空但不得凭作者/正文虚构去重键。按批记录 `expected_count,parsed_count,valid_count,invalid_count,unknown_count,schema_version,missing_field_rates`。缺失 widget、格式漂移或 200 静默空包标记为 `empty_suspect/invalid`，不当成功。

**测试通过条件（T6–T8）**：离线用例分别证明速率/并发/日预算不会超限、日志无敏感数据、每次请求都有终态、聚合可对账、存储故障会终止、库存 0/NULL/封顶语义正确、评论异常值被隔离。真实 12h 测试另需授权与已验证的告警链路。

## File Map

| 路径 | 责任 |
|---|---|
| `collector/benchmark/cookie_supply.py`、`fingerprint.py` | Cookie 供给门与机型池；所有在线任务的硬前置 |
| `docs/superpowers/evidence/buyer-source-matrix.md` | Kit 与 crawler-local 冲突裁决、合同/证据状态 |
| `samples/benchmark/buyer_inventory_page.json`、`buyer_reviews_widget.json` | 去敏可公开的合成/获准 golden 示例 |
| `collector/benchmark/contracts.py`、`outcomes.py` | 规范记录与响应结果分类 |
| `collector/benchmark/policy.py` | 固定限额、会话门禁与停止策略 |
| `collector/benchmark/adapters.py` | 仅通过注入的 Transport 获取数据、复用 Kit 纯解析 |
| `collector/benchmark/store.py` | Run/15分钟摘要/抽样观测的持久化，避免全量请求写业务主表 |
| `collector/benchmark/metrics.py`、`report.py` | Prometheus 与脱敏 JSON/Markdown 报告 |
| `collector/benchmark/runner.py`、`cli.py` | 单进程 12h 运行和安全退出 |
| `collector/storage/models.py`、`alembic/versions/f92b0c1d873e_buyer_benchmark_runs.py` | 基准测试独立 PG 表 |
| `docs/benchmark/buyer-12h-runbook.md` | 预检、启动、熔断、验收、日容量估算 |
| `tests/test_buyer_*.py` | 分组件与端到端离线测试 |

### Task 0: Cookie 供给门（前置，所有在线任务都依赖它）

没有 Cookie 就没有一次成功请求，所以这一层必须先于适配器和运行器落地。它不是「绕过手段」，是数据源接入件。

**Files:**
- Create: `collector/benchmark/cookie_supply.py`
- Create: `collector/benchmark/fingerprint.py`（机型池，vendored 自 `ozon-cookie-harvester` 的 `ozon_cookie/profiles.py`）
- Create: `tests/test_cookie_supply.py`

**Interfaces:**
- `CookieSupply.mint(profile_hint: str | None) -> Session`：裸起 Chromium，CDP 四项同批下发，过挑战后导出 cookie。
- `CookieSupply.lease() -> Session`（least-used）、`mark_dead(session_id)`、`replenish(watermark: int)`。
- `Session(id, cookie_header, ua, impersonate, profile_id, minted_at, use_count, state)`。
- 机型参数复用 `profiles.pick()` / `cdp_override()` / `emulation_metrics()`，不在这里另写一套指纹逻辑。

**Technical constraints（全部来自实测，不要改）:**
- 必须 `connect_over_cdp` 挂载裸起实例；框架自启浏览器会被判自动化并直接 403。
- headless 可用，但前提是 `Network.setUserAgentOverride` 的 `userAgent`、`acceptLanguage`、`platform`、`userAgentMetadata` **四项同批下发**。只设 UA 字符串会让 `sec-ch-ua-platform` 仍报宿主真实平台，形成「页面说 Mac、请求头说 Linux」的矛盾。
- **不带任何 proxy 参数**，加 `--no-proxy-server`，并确认环境里没有残留 `HTTP_PROXY` / `HTTPS_PROXY`。用户已多次否决代理。
- 早停判据：`abt_data` 长度 ≥ 580、连续两次不变、且页面 URL 含 `abt_att=1`。只看长度会拿到半成品，下游用它会 403。
- 内存估算用 PSS 不累加 RSS；单实例约 500 MB。

- [ ] **Step 1: Write failing tests.** 池空时 `lease()` 抛错而**不**自动 mint（避免隐式开浏览器）；连续 lease 取 least-used；`mark_dead` 后该 session 不再被租出且计数不清零；`replenish(watermark)` 补齐到水位；序列化后的事件里不出现 `cookie_header` 明文；`fingerprint.audit()` 能拦下跨机型拼出来的组合。
- [ ] **Step 2: Run** `pytest -q tests/test_cookie_supply.py`，确认 FAIL。
- [ ] **Step 3: Implement.** 预热走 CDP；cookie 只持久化 `cookie_header` 与元数据，不保留浏览器 profile 目录；403 归因用单请求探针 + 约 100 s 冷却，区分「票据过期」与「瞬时并发挤占」；`30 次额度` 作为可配置常量，实验结束后按实测值调整。
- [ ] **Step 4: Run** `pytest -q tests/test_cookie_supply.py`，确认 PASS。
- [ ] **Step 5: Commit** `git add collector/benchmark/cookie_supply.py collector/benchmark/fingerprint.py tests/test_cookie_supply.py && git commit -m "feat: add cookie supply gate as V2 procurement prerequisite"`。

**验收**：`python -m collector.benchmark.cookie_supply --mint-once` 在 5 s 内产出一枚可用 session，且任何日志文件里搜不到 cookie 明文。

---

### Task 1: Lock source-of-truth, page contexts and offline fixtures

**Files:**
- Create: `docs/superpowers/evidence/buyer-source-matrix.md`
- Create: `samples/benchmark/buyer_inventory_page.json`, `samples/benchmark/buyer_reviews_widget.json`
- Create: `tests/test_buyer_contract.py`
- Create: `collector/benchmark/__init__.py`, `collector/benchmark/contracts.py`

**Interfaces:**
- Produces `InventoryObservation(sku, page_path, source, region, observed_at, stock_proxy_max_items, stock_text_remaining, raw_field_paths)` and `ReviewObservation(sku, review_id, score, observed_at, source)` (no personal identifiers required).
- **两个库存字段必须并列，不合并成单个 `stock_proxy_value`**：`maxItems` 在超过 2000 时会封顶到 2000；tile 文案 `textDS` 里的「N ед осталось」才是真实剩余。合并成一个字段会在爆款上得到一条恒定 2000 的假数列，看起来像数据不动，实际是字段到顶。
- Produces `validate_inventory_record(data: dict) -> InventoryObservation` and `validate_review_record(data: dict) -> ReviewObservation`; missing fields stay `None`.

- [ ] **Step 1: Write failing contract tests.** `tests/test_buyer_contract.py` 至少包含：
  - `test_max_items_is_proxy_not_physical`：输入 `maxItems=1011`，输出 `stock_proxy_max_items==1011`，且不存在 `physical_stock` 字段。
  - `test_capped_max_items_keeps_text_value`：输入 `maxItems=2000`、文案「3359 ед осталось」，断言 `stock_proxy_max_items==2000`、`stock_text_remaining==3359`、`is_capped==True`。这条直接锁住封顶行为，防止后来者把两个字段合并回去。
  - `test_unknown_stock_stays_null`：缺 `maxItems` 且无文案时两字段均为 `None`，不得写成 0。
  - `test_noninteger_or_negative_stock_invalid`、`test_capped_inventory_is_not_physical`、`test_review_score_range_and_null`、`test_missing_review_id_does_not_invent_dedupe_key`。
- [ ] **Step 2: Run** `pytest -q tests/test_buyer_contract.py` and confirm tests FAIL (missing module/contracts).
- [ ] **Step 3: Create** `contracts.py` dataclasses and normalization validators，带 `schema_version`、`field_status`、`is_capped` 与批次质量计数。Document **Kit** path/func (`ozon_buyer/collector.py:extract_skus_from_page`, `ozon_buyer/http.py:parse_tile`, `ozon_buyer/detail.py:parse_reviews`), actual query/page contexts and ambiguous alternatives. **fixture 用实测响应脱敏，不要用合成样本**：合成样本只能验证解析器不崩，验证不了封顶行为、文案格式与跨页差异。至少保留三种轮廓——① 常规 SKU（`maxItems` 与文案一致）、② 爆款（`maxItems==2000` 但文案 3000+）、③ 缺失 `maxItems` 的商品卡。脱敏指去掉卖家名、URL 参数、图片地址，保留 widget 结构与数值字段。List `ozon-crawler-local/docs/api/C01-buyer-entrypoint-widget.md` as secondary reference only. Link source commit and fixture SHA256. Explicitly disallow assuming a SKU-only PDP contains listing-page stock.
- [ ] **Step 4: Run** `pytest -q tests/test_buyer_contract.py` and confirm PASS.
- [ ] **Step 5: Commit** `git add collector/benchmark/__init__.py collector/benchmark/contracts.py tests/test_buyer_contract.py samples/benchmark docs/superpowers/evidence && git commit -m "test: lock buyer inventory and review data contracts"`.

### Task 2: Classify outcomes and sanitise event logs

**Files:**
- Create: `collector/benchmark/outcomes.py`, `collector/benchmark/events.py`
- Create: `tests/test_buyer_outcomes.py`

**Interfaces:**
- Consumes `HTTP status`, `response content-type`, `parsed envelope`, `expected widget kind` (not authenticated headers).
- Produces `classify_buyer_response(status_code: int, content_type: str, body: object, kind: str) -> Outcome`, where Outcome is `ok | empty_valid | empty_suspect | blocked | transient_error | invalid`.
- Produces `safe_event_dict(event: RequestAuditEvent) -> dict` (only the Runtime Contract whitelist; no URL, headers, response bodies, authors or secrets).
- Produces `EventLog.append(event: RequestAuditEvent) -> None` and `EventLog.reconcile(run_id: str, expected_attempts: int) -> bool` (rotated, durable JSONL; one terminal event per attempt; fail-closed).

- [ ] **Step 1: Write failing tests** for 200+valid tile, 200+valid explicit EOF, 200+missing widget, 403/429/redirect/challenge, invalid JSON, 5xx; assert ambiguous empty = `empty_suspect` and access-restricted = `blocked`. Test a response containing `cookie`, `authorization`, token-bearing URL and review author does not appear in event serialization. Add `test_one_terminal_event_per_attempt`, `test_log_write_failure_halts_run`, and `test_log_interval_count_reconciliation`.
- [ ] **Step 2: Run** `pytest -q tests/test_buyer_outcomes.py` to observe FAIL.
- [ ] **Step 3: Implement** classification using existing `collector/errors.py` safety semantics; only accept `empty_valid` with explicit terminal evidence from Kit fixtures; all ambiguous empties fail closed. JSONL event writer only serializes `safe_event_dict` (no raw exception text); rotates by day/size, 30-day-or-shorter retention; a failed append raises `StorageUnavailable`.
- [ ] **Step 4: Run** `pytest -q tests/test_buyer_outcomes.py` to PASS.
- [ ] **Step 5: Commit** `git add collector/benchmark/outcomes.py collector/benchmark/events.py tests/test_buyer_outcomes.py && git commit -m "feat: classify and sanitise buyer benchmark events"`.

### Task 3: Define fixed policy and authorised transport boundary

**Files:**
- Create: `collector/benchmark/policy.py`
- Create: `config/benchmark/buyer-inventory.example.yaml`, `config/benchmark/buyer-reviews.example.yaml`
- Create: `tests/test_buyer_policy.py`

**Interfaces:**
- Produces `load_benchmark_policy(path: str, mode: str) -> BenchmarkPolicy` with `source_id`, `kind`, `allowed_endpoint`, `max_rps`, `burst`, `max_concurrency`, `min_interval_seconds`, `max_requests`, `max_requests_per_day`, `duration_seconds`, `license_ref`, `retention`, `mode`, `policy_version`, `cookie_watermark`, `cookie_max_uses`。
- Produces `require_live_authorization(policy: BenchmarkPolicy) -> None`; when mode=live and explicit verified policy fields are absent, raises `PolicyViolation`.
- Produces `BudgetLimiter.acquire(source_id: str, *, clock) -> Permit` and `BudgetLimiter.release(permit: Permit) -> None`, recording wait and refusal reason.

- [ ] **Step 1: Write failing tests**: 缺预算时回落到保守起步值（单进程 20 并发、单 cookie 30 次、HTTP 4.6 页/秒）而非直接拒绝；`cookie_watermark < 1` 或 `cookie_max_uses < 1` 被拒；离线完全不触网；单个票据 403/429 触发**该票据**熔断而非整源停机；不因失败自动提速；库存与评论策略各自独立、不共享预算。同时加入 fake-clock 用例：`test_rps_and_burst_enforced`、`test_run_and_daily_budget_block`、`test_shared_budget_across_tasks`、`test_review_inventory_limits_are_isolated`、`test_retries_consume_budget`。
- [ ] **Step 2: Run** `pytest -q tests/test_buyer_policy.py` to FAIL.
- [ ] **Step 3: Implement** validation and typed policy. YAML examples contain **no guessed numerical online limits**; online values must be copied from Kit evidence + verified licensed policy, with `authorized: false` by default. Single-process budget ledger uses monotonic time and one shared permit per source; any retries/failed attempts count. Shared Redis permit (`collector/rate_limit/distributed.py`) requires separate integration tests before multiple processes; no implicit five-worker experiment.
- [ ] **Step 4: Run** `pytest -q tests/test_buyer_policy.py` to PASS.
- [ ] **Step 5: Commit** `git add collector/benchmark/policy.py config/benchmark tests/test_buyer_policy.py && git commit -m "feat: gate buyer benchmarks by explicit source policy"`.

### Task 4: Build the isolated inventory/review benchmark adapters

**Files:**
- Create: `collector/benchmark/adapters.py`
- Create: `tests/test_buyer_adapters.py`
- Modify: `pyproject.toml` (add optional `buyer-benchmark` extra if existing Kit pure parsers require import-time `curl_cffi`)

**Interfaces:**
- Consumes `BuyerTransport.fetch_page(page_path: str, session: Session) -> ResponseEnvelope`（注入实现；测试默认 Fake），plus Kit pure parsers。在线 Transport 只从传入的 `Session` 取 `cookie_header` / `ua` / `impersonate`，自己不做预热、不换出口。
- Produces `collect_inventory_page(transport: BuyerTransport, page_path: str, wanted_skus: set[str], observed_at: datetime) -> list[InventoryObservation]`.
- Produces `collect_review_page(transport: BuyerTransport, sku: str, page_path: str, observed_at: datetime) -> list[ReviewObservation]`.

- [ ] **Step 1: Write failing tests**: 8 inventory tiles contains only requested 3 SKUs → 3 observations with page provenance; absent desired SKU → no invented zero; valid reviews widget maps 2 records; invalid review scores/missing IDs flagged; schema-version drift produces validation issue rather than success; wrong/missing widget → `empty_suspect`, not empty success; no network is attempted by fixtures.
- [ ] **Step 2: Run** `pytest -q tests/test_buyer_adapters.py` and confirm FAIL.
- [ ] **Step 3: Implement** adapters wrapping Kit `extract_skus_from_page` / `parse_reviews`。会话由 Task 0 的 `CookieSupply` 注入，这里不直接调用 `BuyerClient.ensure_creds`、`PoolClient`、`cdp_warmup`。如果导入旧解析器需要 `curl_cffi`，就加进显式 optional extra 而不是依赖全局安装；验证导入不触发网络。Transport 边界保持显式：Fake/OfflineTransport 永远可用；在线 HTTP Transport **借用 session 的 `impersonate` 档位**（TLS 与 UA 版本对齐是必须的，不算伪造身份）、**跟随重定向**（搜索页 302 → `page_changed=true` 是正常行为，`allow_redirects=False` 会误判成 0 字节失败）、不自行解挑战（挑战由供给门负责）、不轮换代理或身份。某票据 403 就结束该 session 并向池申请下一枚，不重试同一枚。Kit 失败时不静默 fallback 到 crawler-local 的端点。
- [ ] **Step 4: Run** `pytest -q tests/test_buyer_adapters.py` to PASS.
- [ ] **Step 5: Commit** `git add collector/benchmark/adapters.py tests/test_buyer_adapters.py pyproject.toml && git commit -m "feat: isolate buyer inventory and review sample adapters"`.

### Task 5: Persist experiment runs, intervals and limited samples

**Files:**
- Modify: `collector/storage/models.py`
- Create: `alembic/versions/f92b0c1d873e_buyer_benchmark_runs.py` (`down_revision='78a91cdf1b16'` on current main; verify head again before applying)
- Create: `collector/benchmark/store.py`
- Create: `tests/test_buyer_benchmark_store.py`

**Interfaces:**
- Defines `BenchmarkRun(run_id, kind, source_id, mode, started_at, stopped_at, status, stop_reason, policy_hash)`.
- Defines `BenchmarkInterval(run_id, window_start, requests, records, ok, empty_valid, empty_suspect, blocked, error, latency_p50_ms, latency_p95_ms, latency_p99_ms, bytes_received)`, unique `(run_id, window_start)`.
- Defines `BenchmarkSample(run_id, kind, source_id, sku, page_path, observed_at, value, raw_sha256)` with strict sample quota; no raw reviews/author fields in PG. `BenchmarkInterval` also stores `valid_count`, `invalid_count`, `unknown_count`, `missing_field_rates`, `schema_version`, `policy_version`, `audit_event_count`.
- Produces `BenchmarkStore.start_run()`, `upsert_interval()`, `save_sample()`, `finish_run()`.

- [ ] **Step 1: Write failing tests** for two windows, repeated interval write (one row), null stock value preserved, cross-date snapshots kept distinct, interval totals reconcile with terminal events, retention purge works, failed persistence prevents completed status, no secret fields.
- [ ] **Step 2: Run** `pytest -q tests/test_buyer_benchmark_store.py` → FAIL.
- [ ] **Step 3: Implement** models, migration and store. Write raw response only to approved MinIO location with hash/retention when explicitly permitted; otherwise store only safe digests/metrics; implement 30/180/7-day-or-shorter retention and size cap. Reuse existing PG instead of new database. No product/Keyword master-upserts during benchmark.
- [ ] **Step 4: Run** `pytest -q tests/test_buyer_benchmark_store.py` and `DATABASE_URL=sqlite:////tmp/ozon-buyer-bench-migration.db alembic upgrade head` → PASS / latest revision `f92b0c1d873e`; production PG migration requires separate check.
- [ ] **Step 5: Commit** `git add collector/storage/models.py alembic/versions/f92b0c1d873e_buyer_benchmark_runs.py collector/benchmark/store.py tests/test_buyer_benchmark_store.py && git commit -m "feat: persist benchmark runs and intervals"`.

### Task 6: Metrics, 15-minute snapshots and output report

**Files:**
- Create: `collector/benchmark/metrics.py`, `collector/benchmark/report.py`
- Create: `tests/test_buyer_benchmark_report.py`

**Interfaces:**
- Produces `BenchmarkMetrics.record(outcome: Outcome, duration_seconds: float, records: int, bytes_received: int) -> None` and `BenchmarkMetrics.serve(port: int) -> None` (local metrics endpoint via `prometheus_client`, only when enabled) with bounded `source/kind/outcome` labels; never use SKU or URL as Prometheus label.
- Produces `build_benchmark_report(run: BenchmarkRun, intervals: list[BenchmarkInterval]) -> dict` and `render_markdown_report(report: dict) -> str`.

- [ ] **Step 1: Write failing tests** with 15-minute windows verifying request rate, permit waits, peak source concurrency, actual/source cap utilization, valid/invalid/unknown-field counts, request-log-summary reconciliation, effective rows/h, failure buckets, P50/P95/P99 based on raw durations and duration-weighted capacity, complete vs stopped status; ensure report has no raw user comments or tokens.
- [ ] **Step 2: Run** `pytest -q tests/test_buyer_benchmark_report.py` → FAIL.
- [ ] **Step 3: Implement** monotonic timers / UTC boundaries, bounded cardinality counters/histograms, optional loopback metrics scrape endpoint, interval flush every 900 seconds, minimal JSON + Markdown reports with per-field validation warnings and event counter reconciliation. Report original license/policy version, 12h actual runtime, p95 trend, error rates, source-specific sustainable throughput and **uncertainty**; never claim 5× scaling or “physical stock accuracy”.
- [ ] **Step 4: Run** `pytest -q tests/test_buyer_benchmark_report.py` → PASS.
- [ ] **Step 5: Commit** `git add collector/benchmark/metrics.py collector/benchmark/report.py tests/test_buyer_benchmark_report.py && git commit -m "feat: report 15-minute buyer benchmark intervals"`.

### Task 7: 12-hour runner, safe stop and executable CLI

**Files:**
- Create: `collector/benchmark/runner.py`, `collector/benchmark/cli.py`
- Create: `tests/test_buyer_benchmark_runner.py`

**Interfaces:**
- Consumes `BenchmarkPolicy`, `CookieSupply`, injected `BuyerTransport`, `BenchmarkStore`, `BenchmarkMetrics`, `clock`。运行器不自己 mint，只向供给门租借；池枯竭时按策略暂停等待补池，不降级成无会话请求。
- Produces `async run_experiment(policy: BenchmarkPolicy, adapter, store, metrics, *, clock) -> BenchmarkSummary`; **no live transport is auto-created**.
- CLI: `python -m collector.benchmark.cli --mode offline --kind inventory --policy config/benchmark/buyer-inventory.example.yaml --fixture samples/benchmark/buyer_inventory_page.json --duration-seconds 60`; permitted live invocation must pass an explicit approved connection config and no default live mode.

- [ ] **Step 1: Write failing tests** for 1-minute fake-clock offline run, fixed 900s interval flush, manual stop/SIGTERM, 12-hour time boundary, no successful completion on write failure, no re-entry when blocked, exact run/day budget enforcement, 15-minute flush, audit-log failure stopping new requests, and no rate adaptation on errors.
- [ ] **Step 2: Run** `pytest -q tests/test_buyer_benchmark_runner.py` → FAIL.
- [ ] **Step 3: Implement** single-process bounded async loop; always check policy, source state and monotonic deadline **before** acquiring next request; obtain `BudgetLimiter.acquire` before every attempt, persist one terminal event for each attempt; backpressure when sink is slow. Stop with `completed` only at natural time limit with all metrics flushed; otherwise `stopped/blocked/failed`, with partial report and checkpoint. Use no endless auto retries.
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
- [ ] **Step 3: Implement** runbook with (a) Kit/Crawler source matrix and endpoint validation, (b) independent inventory/reviews rps/burst/concurrency/min interval/run/day budgets, (c) offline-first preflight, (d) 单进程 12h 运行排期, (e) 15min summary/Prometheus + alert receiver test, (f) pause/abort runbooks, (g) acceptance and retention policy, (h) output for Worker sizing, (i) log rotation/retention, (j) request-event-summary reconciliation and field-validity reporting. Document that a live run requires the supply gate passing a 20-mint smoke test plus a filled source budget；预算缺省时用保守起步值并标 `estimated`，不以「缺少外部授权文件」为由阻断。
- [ ] **Step 4: Run** `python -m pip install -e '.[test,buyer-benchmark]' && pytest -q tests/test_buyer_*.py && pytest -q` (if the optional extra is needed, else `.[test]`); run offline smoke CLI in short duration; run PG/Redis/MinIO + Alertmanager integration in an approved environment separately, *not* claim success from mocks.
- [ ] **Step 5: Commit** `git add tests/test_buyer_benchmark_e2e.py docs/benchmark/buyer-12h-runbook.md docs/collector-runtime.md && git commit -m "docs: validate and hand off buyer 12-hour benchmark"`.

## Preflight Gate for Actual 12h Online Run

- [ ] 确认 Cookie 供给门能稳定产出会话：连续 20 次 mint 无失败、单次 ≤ 5 s、日志无 cookie 明文。填入库存源源级预算：`max_rps` / `max_concurrency` / `max_requests` / `cookie_watermark` / `cookie_max_uses`。预算空缺时用保守起步值（20 并发、单 cookie 30 次）并在报告里标 `estimated`。
- [ ] 同样为**评论源**独立提供上述政策；不共享或继承库存源预算。
- [ ] 基于 Kit 正确版本的人工审阅通过，确认源矩阵中无未经裁决的关键字段/端点冲突；`ozon-crawler-local` 的任何限速、库存结论不进入批准的在线参数。
- [ ] 运行时日志脱敏、轮转/留存清理、终态事件与 15 分钟汇总对账、字段验证、PG/MinIO 真实写入、告警发送链路、CPU/内存/磁盘空间和人工急停已验证。
- [ ] 先跑 Mock / offline / 低频短跑；若持续被挑战或拒绝（同一票据熔断后，池内连续 3 枚仍 403），停源并标 `blocked`，不硬跑满 12h。
- [ ] 12h 结束后核对事件总数、15min interval 总数（正常 48 个完整窗口）、错误分布、抽样响应 hash 与数据库 idempotency；整理吞吐区间，不自动上调速率。

## Plan Self-Review / Execution Handoff

- **Spec coverage**：字段契约 (T1)、每请求日志及错误分类 (T2)、源级限速/日预算 (T3)、库存和评论字段漂移 (T4)、日志/聚合/留存与对账 (T5)、质量指标 (T6)、12h 严格预算停止 (T7)、可重复验收 (T8)。
- **Boundary**：不触碰后台 P6/P7/P8，不实现正式分布式 Worker，不假定库存准确，不默认线上请求。
- **Execution choice**：建议 **Subagent-driven**（每个任务单独复核；源可信度/权限/数据质量失败成本高）。用户审阅本 Plan 后再选执行方式，随后按 Superpowers skill 实施。
