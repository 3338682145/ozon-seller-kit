# 21 — 每次运行可用工具与资源清单（Runtime Resource Manifest）

版本：OMI-RUNTIME-1.0  
目标项目：Supabase eohvguguegxbhszvssbd  
GitHub：3338682145/ozon-seller-kit

## 1. 每次任务启动必须读取的资源

### A. GitHub项目上下文（必读）
仓库路径：project/ozon-market-intelligence/

1. README.md — 项目入口、当前架构和文档地图。
2. PROJECT-STATUS.md — 当前真实进度、阻塞和数据迁移状态。
3. DECISIONS.md — 已批准决策，不可自行推翻。
4. HANDOFF.md — 上次工作交接、下一步执行顺序。
5. 02-DATA-CONTRACT.md — 字段、来源、类型和时间口径。
6. 03-METRICS-AND-FORMULAS.md — 当前公式版本。
7. 最新数据库审计和市场计算报告（按任务读取）。
8. 17-KEYWORD-CLUSTERING-V2-EXPERIMENT-AND-ACCEPTANCE.md — V2聚类任务必读。
9. 20-MASTER-SYSTEM-PROMPT.md — 项目行为规范。
10. 本文件与22号上下文持久化说明。

不要每次读取整个仓库。先读README、STATUS、DECISIONS、HANDOFF，再按任务加载相关文件。

### B. Supabase资源（正式数据源和计算环境）
Project ID：eohvguguegxbhszvssbd  
Project URL：https://eohvguguegxbhszvssbd.supabase.co  
PostgreSQL：17.6

Schemas：
- ozon_raw：原始数据，只读消费、按snapshot_id追加。
- ozon_analytics：计算结果，按run_id版本化。
- ozon_meta：快照、运行、上下文、决策、提示词和审计元数据。

核心工具：
- mcp__Supabase__get_project：检查项目状态/版本。
- mcp__Supabase__list_tables：读取schema、表、列和约束。
- mcp__Supabase__execute_sql：查询、聚合、验证和受控DDL。
- mcp__Supabase__get_advisors：检查安全和性能建议。
- mcp__Supabase__list_extensions：检查已启用扩展。
- mcp__Supabase__query_logs：按需查看Postgres/API日志。
- mcp__Supabase__get_project_url：确认项目URL。
- mcp__Supabase__generate_typescript_types：应用开发时生成类型。

每次任务至少执行：
1. 查询source_snapshots最新快照及状态。
2. 查询calculation_runs最近运行及状态。
3. 查询本任务相关表的COUNT(*)、快照日期和唯一键覆盖。
4. 确认需要的表已达到预期行数；未完成导入则停止正式计算。
5. 正式计算在Supabase SQL/数据库端完成，结果落ozon_analytics，事件落ozon_meta。

### C. GitHub工具（治理和版本控制）
- mcp__GitHub__fetch_file：读取指定项目文档/脚本。
- mcp__GitHub__fetch：读取公开GitHub API/仓库元数据。
- mcp__GitHub__search：搜索仓库代码和文档。
- mcp__GitHub__create_file / update_file：新增或更新文档、SQL、脚本。
- mcp__GitHub__fetch_commit：确认提交信息。
每次修改后必须fetch_file读回验证；记录commit SHA。不得把数据库密码、service_role、连接串写入仓库。

### D. Google Drive工具（原始文件与归档）
- mcp__Google_Drive__search：查找用户上传的文件。
- mcp__Google_Drive__list_folder：核对文件夹内容。
- mcp__Google_Drive__get_file_metadata：读取文件大小、修改时间、File ID。
- mcp__Google_Drive__fetch：读取/下载支持的文件。
- mcp__Google_Drive__upload_file / create_folder：用户授权下归档产物。
Google Drive用于原始文件和归档；正式计算数据以已导入Supabase快照为准。Drive文件不可用web搜索替代。

### E. Files / Python / Container（辅助工具）
- files__search/read/find/list/materialize：读取当前对话、Project或已连接文件。
- Python：文件完整性、SHA256、格式检查、导入包准备、结果展示。
- Container：文件打包、解压和本地脚本测试。
这些工具不是正式数据计算的权威环境。未经用户明确授权，不得在本地重新计算后声称结果来自Supabase。

### F. Web（只用于公开信息）
仅用于最新公开规则、Ozon政策、Supabase官方文档或用户明确要求的外部研究。
不得使用web访问或替代私有Google Drive、Supabase私有数据、GitHub私有文件。

## 2. 每次运行的标准顺序
1. 读取GitHub README、PROJECT-STATUS、DECISIONS、HANDOFF。
2. 读取20号Master Prompt及相关数据契约/公式/实验方案。
3. Supabase检查项目、schema、快照、运行状态和数据表行数。
4. 对数据完整性进行Gate判断：缺表、行数不符、快照混杂、关键字段缺失时停止正式计算。
5. 建立唯一run_id，记录输入snapshot_id、源SHA、公式版本、参数和工具清单。
6. 使用Supabase SQL执行集合式计算；避免把大表拉进聊天上下文。
7. 验证行数、主键、关联率、NULL、计算不变量和历史基线。
8. 写入ozon_analytics和ozon_meta。
9. 更新GitHub进度、决策、结果报告和HANDOFF。
10. 读回验证GitHub；最终向用户说明完成项、未完成项和阻塞。

## 3. 查询性能约束
- 先聚合后返回，不把177k/百万行明细直接输出到对话。
- 使用CTE、JOIN、GROUP BY、窗口函数和临时/物化中间表。
- 对常用过滤/关联字段建立经验证的索引：snapshot_id、keyword、sku、cluster_id、position、seller_id、run_id。
- 对大批量相似度运算，优先在Supabase生成倒排索引/稀疏关联表，减少关键词两两全表扫描。
- 只有用户明确授权后，才将高密度Embedding任务迁到专用向量服务；向量检索不替代关系型事实核验。
- 每个任务记录SQL耗时、输入行数、输出行数、执行状态。

## 4. 当前已知数据导入状态（运行时必须重新查）
2026-11-02曾出现部分导入状态：部分raw表已到预期行数，sku_power与sku_snapshot_v2未完成，analytics表为0。由于用户正在上传，每次运行必须重新查COUNT(*)，不能沿用旧状态。


## 当前新增P6/P7分析资源（2026-11-02）
- `ozon_analytics.fact_p6_sku_28d`：P6 SKU×28天标准事实层。
- `ozon_analytics.fact_p7_keyword_28d`：P7 query×28天标准事实层。
- `ozon_analytics.bridge_core_keyword_p7`：P8核心关键词到P7 query的精确匹配桥表。
- `ozon_analytics.p6_p7_quality_audit`：P6/P7行数、唯一性、NULL和语义质量审计。
- 最新构建run：`p6_p7_foundation_20261102_v1`；启动后先检查该run的状态及上述4张表行数。
- P7 ca保留raw，语义待核；dyn比较基准未确认。不得把ca当加购人数，或把dyn直接当销量增速。
