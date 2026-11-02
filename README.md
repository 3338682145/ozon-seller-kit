# Ozon 采集与情报分析套件 (`ozon-seller-kit`)

包含两大平铺子模块：
* **`ozon_seller`（卖家后台分析端）**：Cookie Jar 驱动，访问私有 BFF（P6 畅销榜 / P7 搜索词库 / P8 搜索位解释器 / CJM 漏斗），获取真实月销、GMV、广告费率、对手出价。
* **`ozon_buyer`（买家前台采集端）**：免登录、池化高并发，直打页面微前端，获取**真实物理库存上限 (`stock_max`，100%覆盖)**、变体全家桶矩阵、买家评价与 1 星差评排雷、110+ 同款跟卖商工商凭据（ОГРН/公司名）。

> **架构原则：无需嵌套 Git（No Git Submodule）**。两大模块平铺原生管理，各自独立解耦，物理隔离风控，中间通过 `sku` 作为统一主键完成数仓对齐合并。

---

## 模块能力矩阵

| 能力与端点 | 卖家后台端 (`ozon_seller`) | 买家前台端 (`ozon_buyer`) |
|---|---|---|
| **目标域名** | `seller.ozon.ru` / `api.seller.ozon.ru` | `www.ozon.ru` (Entrypoint 微前端) |
| **认证凭据** | **真实店铺 Cookie** (`__Secure-token`，长效) | **匿名临时 Cookie** (自动预热，高并发) |
| **并发吞吐** | 受控单线程 / 低频（防店铺被频控） | 纯 HTTP 极速（50~200 SKU/s，池化可达 300） |
| **真实销量 / GMV** | ✅ **`soldCount` (月销/周销) + `gmvSum`** | ❌ 无此字段（只能通过评价数或动销代理） |
| **实时物理库存** | ⚠️ 后台申报库存 `stock` (含虚拟库存) | ✅ **`stock_max` (加入购物车上限，100%真实)** |
| **对手出价 / DRR** | ✅ **`promotionCpcRate` (CPC出价) + `drr`** | ❌ 无此字段 |
| **变体全家桶** | ❌ 仅返回所查单品 | ✅ **全色系/全尺码关联变体矩阵** |
| **同款跟卖商资质** | ❌ 无 | ✅ **112+ 家跟卖企业名、ОГРН 注册号、城市** |
| **真实买家口碑** | ⚠️ 仅有评分与总评价数 | ✅ **完整评价正文、1星差评排序、买家实拍照** |

---

## 核心接口速查

| 代号 | 端点 / 路径 | 采集内容 |
|---|---|---|
| **p8** (卖家) | `POST /api/search-query-analytics/v2/external/explanation_by_id` | 某词下 108 个搜索位（商品/挂牌价/CPC出价/是否推广） |
| **p6** (卖家) | `POST /api/site/seller-analytics/what_to_sell/data/v3` | 全量 SKU 月销/GMV/均价/drr/申报库存/体积（支持 28天/7天口径） |
| **cjm** (卖家) | `POST /api/search-query-analytics/v1/cjm/get-seller-analytics` | 本店每个 SKU 在搜索链路的漏斗（搜过→看到→点卡→下单→GMV） |
| **search** (买家) | `GET /api/entrypoint-api.bx/page/json/v2?url=/search/...` | 关键词搜索（含 `stock_max` 物理库存上限、`advertLite` 广告标记） |
| **detail** (买家) | `GET /product/<sku>/` + `layout_page_index=2` | 详情画像（价格三件套、变体全家桶、全量属性、富文本HTML、大促库存） |
| **reviews** (买家)| `GET /product/<sku>/reviews/?sort=score_asc` | 真翻页；`score_asc` 直接置顶 1 星差评排雷（正文/优缺点/实拍照） |
| **offers** (买家) | `GET /modal/otherOffersFromSellers?product_id=<sku>` | 提取跟卖商工商凭据（企业主体全称、ОГРН/ОГРНИП 注册号、到底报价） |

---

## 快速开始

```bash
# 1. 卖家后台端：必须探活（需要本地卖家 Cookie）
python3 scripts/check_seller_cookie.py
python3 scripts/collect_seller_p6.py --skus-file skus.txt --period monthly
python3 scripts/collect_seller_p8.py --words-file words.txt --out data/p8.jsonl

# 2. 买家前台端：免登录高并发采集
# 关键词搜索 + 物理库存上限 (stock_max) + 1 星差评排雷
python3 scripts/collect_buyer.py --keyword "сквиш" --pages 2 --reviews 1 --sort score_asc --out data/buyer.json

# 单品/多品深度抓取物理库存与差评
python3 scripts/collect_buyer.py --sku 5081332378 --sku 5527434733 --reviews 2 --sort score_asc --out data/sku_audit.json
```

## Python API 调用示例

```python
# 卖家端
from ozon_seller import SellerClient
seller = SellerClient()
p6_items = seller.what_to_sell(limit=50, period="monthly")

# 买家端
from ozon_buyer import BuyerClient
buyer = BuyerClient()
buyer_items = buyer.search("сквиш", pages=2)
pdp_detail = buyer.sku_detail("5527434733")
reviews_1star = buyer.sku_reviews("5081332378", sort="score_asc")
offers = buyer.other_offers("5527434733")
```

## 数据

`data/toys-slim.db` —— 某俄语站玩具类目（антистресс игрушка）的真实快照，四张表：

| 表 | 行数 | 内容 |
|---|---|---|
| `kw_metrics` | 1,642 | 词级：搜索量/增长/竞争/CR4/覆盖率/同质度/滞销率 |
| `kw_positions` | 177,063 | **每个词的 108 个搜索位**：keyword × sku × position × price × cpc |
| `sku` | 29,823 | SKU 级：月销/GMV/均价/drr/库存/体积/评分/上架日 |
| `clusters` | 165 | 词簇（赛道） |
| `sku_weekly` | 4,350 | **7 天口径**：月销/周销/加速比（周销×4÷月销，>1.15 说明在反弹） |

配合 `docs/SOP-选品流程.md` 可以直接跑选品漏斗。

## 限流（重要，别踩）

| 接口 | 并发 | 实测 |
|---|---|---|
| p8 explainer | **只能 1** | 串行 8.9 词/分钟；并发 ≥2 立刻触发静默空包 |
| p6 what_to_sell | 3-4 | ~3,300 SKU/分钟 |

p8 的限流是**静默的**：HTTP 仍 200、`items` 变空、延迟反而变快（0.2-0.9s）。
**空包请求同样计入配额**，所以「并发 + 重试」等于用废票把窗口灌满。详见 `ozon_seller/README.md` 的实测复盘。

## 数据口径

每个字段的来源、算法、已知缺口都写在 [`docs/DATA-VERIFICATION-12-ITEMS.md`](docs/DATA-VERIFICATION-12-ITEMS.md)，
包含 12 项逐条核查（代码行号 / 实测分布 / 明确标「无出处」的部分）。

要点：
- **批量看**用 p6 的 `drr`（后台直采的广告费占 GMV 比），够用于筛选
- **单品精确看**用 p8 explainer 的 `promotionCpcRate`（每位的 CPC 出价）+ `promotionStatus`
- `CR4` 分母是「108 位里可匹配 p6 的 SKU」，不是全站市场
- 佣金 23% 是**人工假设**，没有平台出处，不能跨类目复用

## Cookie 保活

`__Secure-token` **无法在客户端续期**（实测不轮换，服务端吊销）。能做的是：

```bash
python3 scripts/keepalive_seller_cookie.py            # 探一次（129B / 1.1s 的便宜探针）
bash scripts/install_keepalive_launchd.sh 900         # 每 15 分钟自动心跳
```

失效时退出码 2，串 `scripts/refresh_seller_cookie.sh` 重签。详见 `ozon_seller/README.md` 的「Cookie 保活」节。

## 合法使用

这些是卖家后台自己的接口，只能用于**你自己有权限的账号**。频率控制写死在代码里，请勿提高并发。
公开这份代码是为了让数据工作可复现、可审计，不是鼓励对第三方平台施压。

## License

MIT
