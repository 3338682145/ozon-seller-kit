# 18 — Supabase原始数据与计算结果导入记录（2026-11-02）

## 目标项目
- Supabase project_id：eohvguguegxbhszvssbd
- PostgreSQL：17.6
- 用户已指定：后续正式数据计算均在此Supabase项目执行。
- 本次仅创建隔离schema与空表，不修改public现有业务表。

## 已完成并实测
- 创建schema：ozon_raw、ozon_analytics、ozon_meta。
- 创建原始表：ozon_raw下12张表，字段映射源SQLite。
- 创建分析表：ozon_analytics下5张表（165簇、1642关键词、簇SKU明细、词SKU明细、汇总指标）。
- 创建元数据表：ozon_meta.source_snapshots、ozon_meta.calculation_runs。
- Supabase list_tables读回确认19张表存在，行数目前均为0。
- 验证schema权限：anon_usage=false、authenticated_usage=false（三个schema均如此）；目前没有向客户端开放。
- 安全顾问提示19张表RLS disabled。当前schema USAGE对anon/authenticated已撤销，查询确认这两个角色不能访问；RLS仍建议作为纵深防御后续设置。本轮未擅自启用RLS或添加策略，以免锁住预期的访问路径。

## 源数据指纹与预期行数
### 原始SQLite
- 文件：toys.db
- SHA256：33e5f02961c2782cead58e6714266aab6cbddc31e74242f905d2a7ba218502d8
- 文件大小：128,512,000 bytes
- SQLite quick_check：ok
- 12表总行数：466,767

| 表 | 行数 |
|---|---:|
| blue_v3 | 142 |
| category | 1 |
| dim_cluster | 165 |
| fact_keyword_sku | 177,063 |
| keyword_p7 | 9,979 |
| keyword_score | 2,795 |
| keyword_seerfar | 1,642 |
| keyword_sku | 177,063 |
| product_seerfar | 100 |
| query_metrics_v2 | 1,642 |
| sku_power | 66,352 |
| sku_snapshot_v2 | 29,823 |

### 已计算市场规模SQLite
- 文件：ozon-market-scale-2026-11-02.db
- SHA256：70d6db0a5133c6c484db18453015937b273f1a51d95530274949330dc4033ecc

| 表 | 行数 |
|---|---:|
| cluster_market_165 | 165 |
| keyword_market_1642 | 1,642 |
| cluster_sku_detail | 40,757 |
| keyword_sku_detail | 177,060 |
| market_scale_summary | 39 |

## 导入状态：待客户端批量传输
Supabase MCP当前提供SQL/DDL执行和查询能力，但没有接收本地SQLite二进制文件或执行客户端COPY上传的文件传输工具。Postgres服务器不能直接读取ChatGPT沙箱路径。故本轮没有伪称数据已上传。

已准备导入包：
- 本地归档：ozon-supabase-full-import-kit-2026-11-02.zip
- 包含原始toys.db、计算结果SQLite、COPY批量导入脚本、README和manifest。
- 导入脚本先校验两份数据库SHA256及每张表行数；写入ozon_raw和ozon_analytics；保留snapshot_id/run_id；按表COPY批量传输；导入后逐表count对账；不触碰public业务表。
- 连接方式：用户本机运行脚本，通过Supabase Direct或Session Pooler连接串；不使用Transaction Pooler执行COPY。凭据仅放本机环境变量，不提交GitHub或聊天。

## 版本标识
- snapshot_id：toys_2026_11_02_33e5f029
- run_id：market_scale_v2_2026_11_02_70d6db0a
- P6快照：2026-10-30，28天窗口
- P7快照：2026-10-29
- 计算口径：P8 position 1–108；Gross/Net-est双口径；缺失结单率不填补。

## 导入完成验收门槛
1. 原始12张表行数逐张与上表一致。
2. 计算4张明细表行数与上表一致，汇总39项齐全。
3. 关键唯一键检查：SKU快照sku唯一；关键词SKU关系(keyword,sku)唯一；分析表主键无重复。
4. 对账P6 gross/net-est汇总、165簇/1642词CR4摘要，与历史本地基线一致。
5. 保存导入开始/完成时间、行数、SHA256、错误日志、Supabase执行耗时。
6. 以上通过后，才能将PROJECT-STATUS标为“原始与计算数据已迁移”。

## 下一步
1. 用户在本地运行导入包中的dry-run。
2. 使用Supabase Direct/Session Pooler连接串正式导入。
3. 将最终导入JSON摘要交回本对话，或提供只读SQL结果。
4. 我在Supabase直接执行行数、唯一性和市场指标对账SQL。
5. 对账通过后，所有后续计算都只在Supabase执行。
