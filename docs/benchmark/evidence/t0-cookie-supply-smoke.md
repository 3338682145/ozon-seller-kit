# T0 Cookie 供给门 — 在线冒烟证据（脱敏）

- 日期：2026-11-09（Asia/Shanghai）
- 分支：`design/v2-buyer-benchmark` @ `8b47ed4`
- 环境：共享 venv `venv-ozon-kit`；chromium `/usr/local/bin/chromium`；Xvfb `DISPLAY=:99.0`
- 判据（**未下调**，按 spec 4.4 原文）：`abt_data` 长度 ≥ 580、连续两次不变、最终 URL 含 `abt_att=1`。

## 结论（observed）

**在线冒烟 BLOCKED。** 当前会话无法通过 Ozon antibot 挑战。「单次 ≤5s 产出可用 session」「连续 20 次 mint 零失败」**未达成**，不伪造通过。headful+Xvfb 对照与 headless 结果一致，证明不是「无头被识别」，而是挑战在当前出口无法完成。

## ① 进程环境与启动参数（打印键集合，不打印值）

- 子进程 env 中已移除 `HTTP_PROXY/HTTPS_PROXY/http_proxy/https_proxy/ALL_PROXY`（仅剩 Doubao 基建自带的 `NO_PROXY/PROXY_SERVER/...` 等键，Chromium 不据此走代理）。
- 启动参数含 `--no-proxy-server: True`。
- 即：浏览器直连，无任何代理参数。

## ② 首跳请求头（CDP Network.requestWillBeSent 抓取）

- 尝试用 CDP 事件流抓取首跳 `User-Agent / sec-ch-ua-platform / sec-ch-ua / accept-language`。
- 结果：浏览器导航本身未完成（页内即断连），一次性脚本的事件流抓取未能稳定落到 Document 请求；**不据此下结论**。真正的判据是 ③ 的 cookie 与 URL。

## ③ 实际导出的 cookie 与 URL（真实数字）

| 探测 | 结果 |
|---|---|
| `curl_cffi` 直连 `GET https://www.ozon.ru/`（无代理） | `307` → `?__rr=1`，Set-Cookie 仅 `__Secure-ETC` |
| 跟随跳转后 | `403`，`<title>Antibot Challenge Page</title>`；`abt_data` 长度 ≈ 384 |
| 裸 Chromium + CDP 四字段 `setUserAgentOverride`（headless） | 标题 `Antibot Challenge Page` 后转 `Похоже, нет соединения`；导出 cookie 名 `[__Secure-ETC, abt_data, abt_data]`；**`abt_data` 长度恒为 485**（< 580）；最终 URL 不含 `abt_att=1` |
| 同一时刻 headful + Xvfb 对照 | **完全相同**：cookie 名一致、`abt_data` 长度 485、同样断连、无 `abt_att=1` |
| 挑战静态资源 `https://st-20.ozonstatic.cn/s3/abt-challenge/style_.css` | `403`（`application/xml`，CDN 侧拒绝） |
| `entrypoint-api` 直连 | `307`/`403 text/html`，无 JSON 业务数据 |

## 归因（observed）

headless 与 headful 结果逐字节一致（abt_len 485、cookie 名集合一致、均断连），排除「无头指纹被识别」。挑战页能加载但其后续校验/静态资源在本会话出口被拒（`st-20.ozonstatic.cn` 403、浏览器断连），`abt_data` 长不到 580、不出现 `abt_att=1`。这与 spec 4.4「4.0s / 9 条 cookie」基线不一致——该基线来自先前可通的环境；本会话不可通。按计划 4.3 标 `blocked`，不降判据、不改等待时间。

## 20 次 mint 冒烟为何未跑

headful 对照已证明两种模式在同一出口结果一致，再跑 20 次只会得到 20 次相同的 485/断连，不新增证据，且每次要等满超时。故未执行；待出口恢复后用最终选定模式（headful+Xvfb）重跑 20 次并逐次记录耗时。

## 因此未做的在线验证（unknown）

- 20 次连续 mint 耗时列表 / 成功率：**未跑**（判定必败，见上）。
- 单页库存 / 单页评论真实响应抓取：**未拿到**（全部 403）。
- 403 冷却 ~100s 恢复、单 cookie ~30 次额度：**未重测**。

## 已交付（离线，observed）

- `collector/benchmark/cookie_supply.py`、`fingerprint.py`、`tests/test_cookie_supply.py`：池空不隐式 mint、least-used、mark_dead 不清零、replenish 到水位、事件不含 cookie 明文、`--no-proxy-server`、代理 env 剥离、`fingerprint.audit()` 拦截跨机型拼装。
- 9 个离线单测全绿（见 commit）。
- 本文件与代码均经 grep 扫描，无 cookie 明文值。
