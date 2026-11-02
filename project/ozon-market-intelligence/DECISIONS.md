# 项目决策记录

## ADR-2026-11-02-01：Supabase作为后续计算执行环境
状态：已获用户确认。
- 目标项目：`eohvguguegxbhszvssbd`。后续正式数据计算、聚类实验、结果存储和对账均在此Supabase执行。
- GitHub `3338682145/ozon-seller-kit`保存SQL、脚本、公式版本、进度、决策、验收摘要与handoff；不存数据库凭据。
- 沙箱/本地仅用于文件接收、导入准备、归档与结果展示；不得静默回退本地计算后声称是Supabase结果。
- 不擅自增加付费服务或迁移到其他计算环境。

## ADR-2026-11-02-02：连接成功不等于数据迁移完成
Supabase PostgreSQL 17.6连接正常。此前目标表不存在。只读核验不代表本批数据已导入。

## ADR-2026-11-02-03：进度、证据与handoff同步保存
每轮保存SQL/配置/说明，执行后记录证据摘要，再同步GitHub并读回核验。run_id、snapshot_id、源SHA、公式版本、输入输出行数和错误必须留档。已设计、已执行、已验证分开标记。

## ADR-2026-11-02-04：原始和计算结果分层导入Supabase
状态：schema已创建，数据导入待客户端执行。
- 隔离schema：ozon_raw、ozon_analytics、ozon_meta。
- 原始数据保留原表结构和字段含义，按snapshot_id保存；分析结果按run_id保存。
- 不修改public既有业务表；不清空或覆盖其他业务数据。
- 源SQLite和派生SQLite以SHA256固定版本；导入前校验指纹和表行数，导入后逐表count核对。
- 导入使用本机客户端COPY，经Direct或Session Pooler连接；凭据只放本机环境变量，不进GitHub或聊天。
- 本轮Supabase MCP没有本地二进制/客户端COPY上传入口，所以已创建表但没有声称数据已上传。导入包和脚本已准备，需运行一次客户端命令。

## ADR-2026-11-02-05：新建Ozon schema访问边界
已撤销anon/authenticated对ozon_raw、ozon_analytics、ozon_meta的schema USAGE。Supabase advisor报告19张新表RLS disabled；本轮查询确认anon_usage=false、authenticated_usage=false。RLS仍是应用接入前的纵深防御要求；本轮未自动启用RLS或添加策略，避免未经确认改变访问模型。

## 保留的业务决定
- 首类目解压玩具；核心分析单位产品族；预测目标30–90天。
- 词簇代表搜索意图市场，不代表精确同款。40%为交集SKU数/较小SKU集合数。
- 每词最多一个Primary，可有Secondary；Secondary不参与市场加总。
- V1的165簇保留；V2为独立离线实验，未验收不得覆盖。
- P6毛订单含取消退货；Net-est按结单率估算，非最终结算账；DRR保留原值并继续做数值质量控制。
