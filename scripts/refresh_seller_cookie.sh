#!/usr/bin/env bash
# 卖家端 cookie 自动刷新链
#
#   1) 探活（纯 HTTP，2-3s）
#   2) 可用 → 什么都不做
#   3) 不可用 → ego-browser 重新 mint（约 25s），再探活确认
#
# 何时真的需要重 mint（实测口径，2026-10-30）：
#   __Secure-token @ .seller.ozon.ru   TTL 8760h（1 年）
#   abt_data       @ .ozon.ru          TTL ~8760h
#   sc_company_id  @ .seller.ozon.ru   TTL session ← 只有这个是会话级
#   所以日常不用刷；触发重 mint 的真实情况只有：
#     · 换店 / 退出登录 / 平台踢会话
#     · token 被风控吊销
#     · 机器换了（jar 与 UA 绑定）
#
# 用法:
#   bash scripts/refresh_seller_cookie.sh          # 需要时才 mint
#   bash scripts/refresh_seller_cookie.sh --force  # 强制重 mint
set -uo pipefail
cd "$(dirname "$0")/.."

FORCE=0
[ "${1:-}" = "--force" ] && FORCE=1

if [ "$FORCE" -eq 0 ]; then
  python3 scripts/check_seller_cookie.py
  rc=$?
  if [ "$rc" -eq 0 ]; then
    echo "=== [seller-cookie] 有效，无需刷新"
    exit 0
  fi
  if [ "$rc" -eq 3 ]; then
    echo "=== [seller-cookie] 被限流，不是 cookie 问题。过 10-20 分钟再试"
    exit 3
  fi
  if [ "$rc" -eq 4 ]; then
    echo "=== [seller-cookie] 网络问题，不刷新"
    exit 4
  fi
  echo "=== [seller-cookie] 鉴权失效 → 重新 mint"
fi

if ! command -v ego-browser >/dev/null 2>&1; then
  echo "✗ 找不到 ego-browser，mint 必须在一台有该浏览器的机器上执行" >&2
  exit 5
fi

MINT_PATH="$(cd "$(dirname "$0")" && pwd)/mint_seller_cookie.mjs" ego-browser nodejs <<'NODE'
await import('file://' + process.env.MINT_PATH);
NODE
mint_rc=$?
if [ "$mint_rc" -ne 0 ]; then
  echo "✗ mint 失败（rc=$mint_rc），检查浏览器里卖家端是否仍登录" >&2
  exit 6
fi

echo "=== [seller-cookie] 复验"
python3 scripts/check_seller_cookie.py
exit $?
