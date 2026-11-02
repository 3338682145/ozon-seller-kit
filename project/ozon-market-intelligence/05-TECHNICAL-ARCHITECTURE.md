# 05 — 技术架构与数据流水线

## 1. 总体架构
建议第一版保持本地优先：Python负责ETL/计算/API，SQLite负责原始与分析数据，DuckDB可作为大规模分析层，前端先用Streamlit或轻量Web UI。不要一开始引入复杂微服务。

[Ozon p6/p8/P7 + Seerfar + 1688报价 + 物流费率]
        ↓
[采集适配器 / CSV与SQLite导入]
        ↓
[Raw immutable layer：原始响应、快照、来源、时间窗口]
        ↓
[Validation & normalization：字段、单位、ID、异常、join质量]
        ↓
[Canonical model：SKU / keyword / seller / product family]
        ↓
[Feature engine：需求、规模、Entry、价格、利润]
        ↓
[Forecast engine：30/60/90天情景与区间]
        ↓
[Decision API + 产品族报告 + SKU明细导出]
        ↓
[Forecast vs Actual：回测与RSI候选改进]

## 2. 建议仓库目录
project/ozon-market-intelligence/
- README.md
- 01-GOAL-AND-PLAN.md
- 02-DATA-CONTRACT.md
- 03-METRICS-AND-FORMULAS.md
- 04-VALIDATION-CHECKLIST.md
- 05-TECHNICAL-ARCHITECTURE.md
- 06-RSI-SELF-IMPROVEMENT.md
- 07-ROADMAP-AND-DELIVERABLES.md
- config/：阈值、类目佣金、物流费率、IP词典
- sql/：schema、质量检查、产品族聚合、Entry指标
- src/ingest/：SQLite/CSV导入、快照采集
- src/normalize/：单位、字段、标题、SKU标准化
- src/family/：候选生成、归并、人工审核
- src/features/：需求、市场、竞争、利润特征
- src/forecast/：基线、模型、区间、回测
- src/decision/：Gate、评分、报告
- tests/：单元、集成、数据回归测试
- outputs/：报告、CSV、审计产物（不提交敏感Cookie）

## 3. 分层存储
1. Raw：只追加，不改写；保留原始数据库副本、CSV、JSON响应、来源和hash。
2. Staging：类型转换、去重、单位统一、坏数据隔离。
3. Core：SKU快照、关键词位置、P7需求、产品族映射。
4. Mart：product_family_market_daily/weekly、keyword_entry_snapshot、sku_unit_economics、forecast_vs_actual。
5. Audit：数据质量、规则版本、人工审核、预测记录。

## 4. 执行频率
- p6：每周刷新候选SKU；如接口配额允许可日更，但严格遵守仓库限流约束。
- p8：对目标关键词按周刷新；p8 explainer严格串行，不以并发换速度。
- P7：按月度数据更新节奏采集，同时保存每次快照。
- 1688报价：候选进入利润层时人工/接口核价，记录报价时间和有效期。
- 物流/佣金：按费率生效日期版本化，费率变更触发利润重算。
- 预测：每周生成30/60/90天预测；窗口成熟后回填实际值。

## 5. API / 页面最小能力
- GET /health：数据版本、最近快照、质量状态。
- GET /families：产品族列表、过滤与排序。
- GET /families/{id}：市场概览、Entry、趋势、利润情景。
- GET /families/{id}/skus：exact/close/broad SKU全清单。
- GET /keywords/{kw}/competition：max_slot30、new_top10、CR4、p25。
- POST /cost-simulation：输入采购、物流、佣金、广告、汇率，返回利润与COGS上限。
- GET /forecasts/{id}：30/60/90天情景和区间。
- GET /exports/{id}.csv：SKU明细和复算字段。

## 6. 版本与安全
- 每次数据导入生成snapshot_id与sha256。
- 每个计算结果绑定formula_version和config_version。
- 原始数据只读；分析结果写入新表。
- Cookie、token、账号信息不得进入Git仓库或报告。
- 所有模型变更先离线测试，再影子运行，人工审批后发布。
