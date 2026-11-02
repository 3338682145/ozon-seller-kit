# Handoff：Ozon Market Intelligence

## 先读
1. [DECISIONS.md](DECISIONS.md)
2. [PROJECT-STATUS.md](PROJECT-STATUS.md)
3. [18-SUPABASE-RAW-DATA-IMPORT.md](18-SUPABASE-RAW-DATA-IMPORT.md)
4. [02-DATA-CONTRACT.md](02-DATA-CONTRACT.md)、[03-METRICS-AND-FORMULAS.md](03-METRICS-AND-FORMULAS.md)
5. [17-KEYWORD-CLUSTERING-V2-EXPERIMENT-AND-ACCEPTANCE.md](17-KEYWORD-CLUSTERING-V2-EXPERIMENT-AND-ACCEPTANCE.md)

## 当前环境
- Supabase project_id：`eohvguguegxbhszvssbd`，PostgreSQL 17.6。
- GitHub仓库：`3338682145/ozon-seller-kit`。
- 后续正式计算必须在Supabase执行。
- 已创建ozon_raw、ozon_analytics、ozon_meta三个schema及19张表；raw和analytics表当前仍为0行。
- anon/authenticated对三个schema均无USAGE权限；RLS尚未启用，应用接入前需加纵深策略。

## 本轮文件与导入状态
- 原始toys.db SHA256：`33e5f02961c2782cead58e6714266aab6cbddc31e74242f905d2a7ba218502d8`。
- 派生市场规模SQLite SHA256：`70d6db0a5133c6c484db18453015937b273f1a51d95530274949330dc4033ecc`。
- 本地导入包：`ozon-supabase-full-import-kit-2026-11-02.zip`，包含两份DB、COPY导入脚本、README、manifest。
- 导入脚本dry-run已在本环境执行成功：两份SHA256匹配；12张原始表与4张计算明细表的预期行数全部匹配。
- 正式导入尚未执行，因为当前Supabase MCP没有将本地SQLite二进制/本地路径推送到Postgres的客户端COPY传输通道。需在用户本机通过Direct或Session Pooler执行导入脚本。

## 下一步
1. 下载并解压导入包。
2. 安装 `python -m pip install "psycopg[binary]>=3.2,<4"`。
3. 从Supabase Dashboard → Connect复制Direct或Session Pooler连接串，在本机设为环境变量SUPABASE_DB_URL。不要使用Transaction Pooler做COPY；不要把密码发到聊天或GitHub。
4. 先执行README中的dry-run，再正式执行脚本。
5. 把最终JSON摘要交回；随后在Supabase执行逐表行数、唯一键、市场汇总独立对账。
6. 只有对账通过后才将迁移标记完成，并在Supabase重算。

## 口径红线
P6毛订单含取消/退货；Net-est按nullableRedemptionRate估算且NULL不填补；P6 salesDynamics是GMV动态；P7 count_28d是独立搜索买家数；P8严格position 1–108；CR4为可观测SKU样本；跨簇总盘SKU全局去重；DRR数值仍需QC；V1不覆盖，V2是搜索意图聚类，L2a同款/跟卖独立建设。

## 当前真实状态
Schema与元数据记录已在Supabase。源数据和计算结果尚未上传；Supabase正式重算尚未开始。
