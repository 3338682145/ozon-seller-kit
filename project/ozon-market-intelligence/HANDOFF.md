# Handoff：Ozon Market Intelligence

## 先读
1. [DECISIONS.md](DECISIONS.md)：执行环境、数据边界与决策。
2. [PROJECT-STATUS.md](PROJECT-STATUS.md)：真实进度与阻塞。
3. [18-SUPABASE-RAW-DATA-IMPORT.md](18-SUPABASE-RAW-DATA-IMPORT.md)：导入结构、指纹、行数、验收。
4. [02-DATA-CONTRACT.md](02-DATA-CONTRACT.md)、[03-METRICS-AND-FORMULAS.md](03-METRICS-AND-FORMULAS.md)：字段与计算口径。
5. [17-KEYWORD-CLUSTERING-V2-EXPERIMENT-AND-ACCEPTANCE.md](17-KEYWORD-CLUSTERING-V2-EXPERIMENT-AND-ACCEPTANCE.md)：V2实验规则。

## 当前环境
- Supabase project_id：`eohvguguegxbhszvssbd`，PostgreSQL 17.6。
- GitHub仓库：`3338682145/ozon-seller-kit`。
- 后续正式计算只能在Supabase执行；不得默认为沙箱/本地Pandas或DuckDB计算。
- 已创建schema：ozon_raw、ozon_analytics、ozon_meta；共19张空表。
- 已核验anon/authenticated对三个新schema无USAGE权限。RLS尚未启用，应用接入前需根据访问模型补策略。

## 本轮数据文件
- 原始：toys.db，SHA256 `33e5f02961c2782cead58e6714266aab6cbddc31e74242f905d2a7ba218502d8`，12张表，466,767行。
- 派生：ozon-market-scale-2026-11-02.db，SHA256 `70d6db0a5133c6c484db18453015937b273f1a51d95530274949330dc4033ecc`。
- 导入包：`ozon-supabase-full-import-kit-2026-11-02.zip`，本地下载后包含两份DB、COPY导入脚本、README和manifest。
- 导入脚本要求本机设置SUPABASE_DB_URL，使用Direct或Session Pooler；不要使用Transaction Pooler执行COPY。密码不得贴入聊天或提交GitHub。

## 下一步（必须按顺序）
1. 下载导入包并解压。
2. 安装 `python -m pip install "psycopg[binary]>=3.2,<4"`。
3. 在本机设置SUPABASE_DB_URL环境变量（Supabase Dashboard → Connect获取）。
4. 先运行脚本 `--dry-run`，核对两份SHA和行数。
5. 正式运行脚本；它会写入隔离schema、保存snapshot_id/run_id并逐表核对。
6. 把脚本最终JSON摘要交回；再通过Supabase SQL独立复核行数、唯一键、市场汇总。
7. 只有对账通过后，才将数据迁移状态标为完成并继续V2实验。

## 重要业务口径
- P6 soldCount/GMV是含取消退货的28天毛订单。
- Net-est逐SKU按nullableRedemptionRate折算；NULL不填0或100%，需报告覆盖率。
- P6 salesDynamics是金额动态；P7 count_28d是独立搜索买家数。
- P8严格position 1–108；CR4是可观测SKU样本口径。
- DRR定义已知但数值质量需继续检查；CPC出价不等于实际扣费。
- 一个SKU可跨需求簇；跨簇总市场必须SKU全局去重。
- V1 165簇不覆盖；V2是搜索意图聚类，不是L2a精准同款产品族。

## 本轮状态
Schema创建已完成；数据导入尚未完成。Supabase表行数目前为0。不能把本地历史计算结果描述为Supabase正式计算结果。
