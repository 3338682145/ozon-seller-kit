# 缺口与禁止虚构项

| ID | 缺口 | 证据/影响 | 动作与门禁 |
|---|---|---|---|
| GAP-001 | P7 在线采集函数未实现 | `ozon_seller/api.py` 无 P7 方法；旧 Supabase 文档有 P7 表，不等于采集端点 | `UnimplementedAdapter` + 测试；仅允许合法文件导入 |
| GAP-002 | Buyer 授权/使用许可未核验 | 旧实现通过挑战获取 Cookie、池化 403 补池 | 在线 Buyer 默认关闭；只跑 Mock/持有许可的原始快照 |
| GAP-003 | Seller 私有网页接口许可未核验 | 使用网页登录态、`seller_id/uuid`，不是官方公开 API | Seller 禁用；需审批、Vault 凭证、授权范围和固定配额 |
| GAP-004 | SQLite 二进制未现场验算 | 上游旧报告：sku=29823、kw_positions=177063、kw_metrics=1642、clusters=165、sku_weekly=4350 | CI 用 SQLite 只读 `PRAGMA integrity_check`、`PRAGMA table_info` 复核；本次不假装已读库 |
| GAP-005 | SKU-变体-商品族映射不足 | 旧报告 P6 约 29,823 SKU，但全量变体/条码缺失 | `product_id_mappings` 保存证据/可信度；不推断同款 |
| GAP-006 | 单一期快照无真实 7/30 天趋势 | 旧数据库主要单期 P6/P7 | 7/30 天趋势指标仅在足够连续同口径快照后计算，否则 NULL |
| GAP-007 | P8 约 19,075 SKU 没有 P6 匹配 | 旧审计的 2026-11-02 快照；不可填零销量 | 保留 unmatched 标识与单独覆盖率 |
| GAP-008 | 关键词簇 308 个未分配，P7 精确映射只命中 560/1642 | 旧审计；禁止直接强制合并 | 未匹配留在 unassigned；人工复核 |
| GAP-009 | 全量 Offers、评论正文、库存时间序列 | 源码有单个 SKU 读取能力，不能证明覆盖 | 逐源授权/时间窗后再开采 |
| GAP-010 | 生产性能、源限额、成功率未知 | README 实验不是生产基准 | Mock benchmark 独立记录；真实源验收需要签署限额和独立性能证据 |
| GAP-011 | DSH SuperAgent 对外协议未提供 | 本仓库无 Ticket/Session/Decision/Assignment/Report API 契约 | 提供内部兼容生命周期和只读 MCP Tools；不能宣称已连外部 DSH |
| GAP-012 | Crawlab API 对接/凭证未提供 | Crawlab 可管理批次，但没有访问配置 | Compose 可选服务 + 批次契约文档；未宣称真正创建上游 Crawlab 任务 |
| GAP-013 | 无生产 Secrets/Vault/备份恢复演练 | 密钥、备份、KMS/审批系统均未接入 | 仅提供 Vault 适配代码/备份脚本/测试；生产部署前需安全验收 |

## 审计新增：Buyer 以图搜图通道

`ozon_buyer/image.py` 有以图搜图上传/解析代码，但依赖 Cookie 预热、浏览器身份模拟以及站点上传接口；未确认授权与合法留存范围。**独立缺口 `buyer_image`**：生产源禁用，不创建自动采集 Adapter；需要明确授权、入参限制、脱敏和测试夹具后再做纯解析适配。
