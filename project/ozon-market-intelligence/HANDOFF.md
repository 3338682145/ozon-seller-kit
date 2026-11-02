# Handoff：Ozon Market Intelligence

## 先读

1. [DECISIONS.md](DECISIONS.md)：当前执行环境及已确认业务边界。
2. [PROJECT-STATUS.md](PROJECT-STATUS.md)：实际完成、阻塞与迁移验收基线。
3. [02-DATA-CONTRACT.md](02-DATA-CONTRACT.md)、[03-METRICS-AND-FORMULAS.md](03-METRICS-AND-FORMULAS.md)：字段和计算口径。
4. [15-MARKET-SCALE-165-1642-2026-11-02.md](15-MARKET-SCALE-165-1642-2026-11-02.md)、[17-KEYWORD-CLUSTERING-V2-EXPERIMENT-AND-ACCEPTANCE.md](17-KEYWORD-CLUSTERING-V2-EXPERIMENT-AND-ACCEPTANCE.md)：历史结果和V2实验方案。

## 当前任务与工具

用户已经指定：后续正式数据计算使用已连接的Supabase，GitHub记录进度、决策、handoff；不要再次询问本地/云端技术选型。
目标Supabase project_id：`eohvguguegxbhszvssbd`。
仓库：`3338682145/ozon-seller-kit`；项目路径：`project/ozon-market-intelligence/`。
本轮连接已验证，但未发现与原始Ozon源表同名的表或ozon% schema。此检查不等于项目为空，不得触碰已有其他业务数据。

## 下一步操作

- 先运行 [sql/verify_supabase_target.sql](sql/verify_supabase_target.sql)，只读确认目标环境。
- 核对现有源文件与版本后再设计导入。历史源：Google Drive `ozon-data/toys.db`，文件ID `1HdWipkSd0f8aw6Zsb_n6-UhnyX_fD_yD`；本地曾归档为 `/mnt/data/ozon-market-intelligence/data-snapshots/2026-11-02/toys.db`，每次先确认路径确实可用。
- 使用隔离schema保存原始快照、派生结果与运行记录；`ozon_raw`、`ozon_analytics`、`ozon_audit`是待实施的命名方案，并非本轮已经建立。
- 通过客户端批量导入文件，不用SQL读取服务器文件，不把大型二进制或大量行直接塞入聊天工具参数。
- 原始数据只追加快照；SKU ID用文本。记录源hash和原始单位。不要为了迁移改变字段含义。
- 优先在库内完成DISTINCT、JOIN、GROUP BY、窗口排名及V2候选对倒排查询，返回摘要而不是全量数据到聊天。必要索引与性能优化先用执行计划和实测验证。
- 对账通过后才继续V2；无正式同款证据时只记录用户提供的anchor SKU/offer SKU/seller关系，不扩大为精确商品族。

## 必须守住的计算细节

- 先按SKU主键去重，再SUM销量/GMV。禁止SUM(DISTINCT sold_count)，它会把销量相等但不同的SKU误删。
- 毛件数/GMV含取消退货；net-est逐SKU乘已知结单率。NULL不填0或100%，必须报告覆盖率。net-est不等于最终结算账。
- 毛/净CR4分别重新排序Top4；SKU CR4与卖家CR4分开。
- 一个关键词或簇命中的SKU销量属于SKU样本总量，不是该关键词直接带来的成交归因量。
- P8严格位置1–108；主簇内SKU取并集；全市场跨簇再去重。一个Primary关键词归属不保证SKU互斥。
- DRR保留原值与质量标记，未实际对账前不当作已验证广告支出；CPC出价不能替代广告账单。
- 不把stock_max购买数量上限或两天差值当作已验证真实库存/销量。

## 每轮交付协议

本地保存SQL/配置/说明 → Supabase执行并验证 → 数据库保留结果和run_id → GitHub更新SQL、进度、决策、handoff → 读回核验 → 汇报已做与未做。

运行记录至少包括：run_id、snapshot_id、source_hash、formula_version、config_version、sql_path/sql_hash、started_at/finished_at、input_rows/output_rows、validation_status、error、artifact_path、git_commit。运行记录表尚待建设，不得声称已有自动任务。

不得提交访问令牌、密码、数据库连接密码、service_role key、Cookie或原始用户账单到GitHub。不要为分析随意开放public/anon权限或修改Auth。已存在业务表保持不变；如需要对外Data API则另行明确授权/RLS规则。

## 本轮结束状态

只完成Supabase只读验证、执行环境决策记录与交接资料；未迁移Ozon数据，未在Supabase运行市场重算/V2聚类，未修改Auth或受保护路由，也未设置后台自动计算。不要把历史本地成果写成云端计算成果。
