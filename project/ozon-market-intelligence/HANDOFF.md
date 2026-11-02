# Handoff：Ozon Market Intelligence

## 先读
1. [DECISIONS.md](DECISIONS.md)
2. [PROJECT-STATUS.md](PROJECT-STATUS.md)
3. [18-SUPABASE-RAW-DATA-IMPORT.md](18-SUPABASE-RAW-DATA-IMPORT.md)
4. [19-SUPABASE-IMPORT-BLOCKER-AND-CLIENT-RUNNER.md](19-SUPABASE-IMPORT-BLOCKER-AND-CLIENT-RUNNER.md)
5. [02-DATA-CONTRACT.md](02-DATA-CONTRACT.md)、[03-METRICS-AND-FORMULAS.md](03-METRICS-AND-FORMULAS.md)

## 当前环境
- Supabase project_id：`eohvguguegxbhszvssbd`，PostgreSQL 17.6。
- GitHub仓库：`3338682145/ozon-seller-kit`。
- 后续正式计算必须在Supabase执行。
- 已创建ozon_raw、ozon_analytics、ozon_meta三个schema及19张表；raw和analytics表当前仍为0行。
- anon/authenticated对三个schema均无USAGE权限；RLS尚未启用，应用接入前需加纵深策略。

## 文件和导入状态
- 原始toys.db SHA256：`33e5f02961c2782cead58e6714266aab6cbddc31e74242f905d2a7ba218502d8`。
- 派生SQLite SHA256：`70d6db0a5133c6c484db18453015937b273f1a51d95530274949330dc4033ecc`。
- 修正版导入包：`ozon-supabase-full-import-kit-2026-11-02-fixed.zip`；SHA256 `efacb91682cf7ead88de5eca59bf77a37f6fcc0ca83ae59ae9ac79e039e3e7a9`。
- 修复了原COPY helper的未定义sql变量；py_compile通过，dry-run通过，原始与派生DB指纹和预期行数全部匹配。
- 本轮Supabase MCP没有本地文件二进制上传或客户端COPY通道；当前沙箱无SUPABASE_DB_URL、psql/psycopg，且Supabase HTTPS域名DNS解析失败。因此助手不能从当前会话直接完成COPY传输。详见19号文档。

## 下一步
需要在可访问Supabase Postgres的客户端运行修正版导入器：
1. 解压修正版ZIP。
2. `python -m pip install "psycopg[binary]>=3.2,<4"`
3. 从Supabase Dashboard → Connect获取Direct或Session Pooler连接串，在本机环境变量SUPABASE_DB_URL中设置；不要贴入聊天或GitHub。
4. 运行README中的dry-run，再正式执行COPY导入。
5. 将最终JSON摘要交回；再用Supabase SQL独立复核逐表行数、唯一键和市场汇总。
6. 只有对账通过后才标记迁移完成并继续正式计算。

## 业务口径红线
P6毛订单含取消/退货；Net-est按nullableRedemptionRate估算且NULL不填补；P6 salesDynamics是GMV动态；P7 count_28d是独立搜索买家数；P8严格position 1–108；CR4为可观测SKU样本；跨簇总盘SKU全局去重；DRR数值仍需QC；V1不覆盖，V2是搜索意图聚类，L2a同款/跟卖独立建设。

## 当前真实状态
Schema与元数据记录已在Supabase。源数据和计算结果尚未上传；Supabase正式重算尚未开始。
