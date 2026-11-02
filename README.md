# Ozon 卖家端采集器（本地 HTTP，不依赖浏览器常驻）

用一份 Cookie jar 打 Ozon 卖家后台的分析接口，把「关键词 → 108 个搜索位 → SKU 销量」整条链采下来。

**核心结论：不需要浏览器常驻。** 浏览器只当「证书签发器」（偶尔取一次 cookie），剩下全在 Python 里跑。

---

## 这套东西解决什么问题

Ozon 卖家后台「分析 → 搜索可见性」里有一张表：某个搜索词下的前 108 个商品位置，含价格、CPC 出价、是否推广。
这张表是选品和投流的核心数据，但后台没有导出，接口又是私有 BFF。

本仓库把它变成可批量、可复现、可离线分析的数据管线。

## 三个接口

| 代号 | 端点 | 拿什么 |
|---|---|---|
| **p8** | `POST /api/search-query-analytics/v2/external/explanation_by_id` | 某个词下 108 个搜索位（商品/价格/CPC/是否推广/主图） |
| **p6** | `POST /api/site/seller-analytics/what_to_sell/data/v3` | 每个 SKU 的月销/GMV/均价/drr/库存/体积/评分（**支持 28 天 + 7 天两个口径**） |
| **cjm** | `POST /api/search-query-analytics/v1/cjm/get-seller-analytics` | 本店每个 SKU 在搜索链路的漏斗（搜过→看到→点卡→下单→GMV） |

## 快速开始

```bash
git clone <this repo> && cd ozon-seller-kit
python3 -m pip install --upgrade pip   # 无第三方依赖，纯标准库

# 1) 拿 cookie（两条路，二选一）
#    A. 用 ego-browser / Chrome CDP 自动签
ego-browser nodejs <<'X'
await import('file://' + process.cwd() + '/scripts/mint_seller_cookie.mjs');
X
#    B. 浏览器插件导出 Cookie JSON，手动放进 ~/.config/ozon-seller/cookie.txt
#       ⚠ 必须包含 abt_data，否则一律 403 fab_chlg（详见 ozon_seller/README.md）

# 2) 探活
python3 scripts/check_seller_cookie.py      # 0=可用 2=鉴权失效 3=限流 4=网络

# 3) 采
python3 scripts/collect_seller_p8.py --words-file words.txt --out data/p8.jsonl
python3 scripts/collect_seller_p6.py --skus-file skus.txt --period monthly
python3 scripts/collect_seller_p6.py --skus-file skus.txt --period weekly
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
