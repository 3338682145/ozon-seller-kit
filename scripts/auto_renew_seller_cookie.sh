#!/usr/bin/env bash
# 卖家端 cookie 自动续签
#
# 背景（2026-11-01 用 REA 逆向 + 实测修正，见 scratch/2026-11-01-ozon-token-refresh-re/REPORT.md）：
#   · 「8 小时一换」不成立。token 第 6 段是 UTC+2 的**最后写入时刻**，不是签发时刻；
#     旧逻辑拿本地时间(UTC+8)去减，恒定得到 ~6h，属于时钟差误判。
#   · 业务 API 200 时**不轮换** `__Secure-token`（6 端点实测 Set-Cookie = 0）。
#   · 页面 reload **不重发** token（同一会话 3 次 reload，字节级不变）。
#   · `POST /api/auth/token/refresh` 在生产是 **404**（已登录页同源 fetch 也 404）。
#   实测寿命：某会话 token 最后写入 2026-09-04，到 2026-11-01 仍 200（>=58 天）。
#
# 所以保活只有一条有效规则：
#   探活 OK  -> 什么都不做（重签只是抄同一份快照，不产生新 token）
#   探活 401/403 -> 只能重新从浏览器 mint
#
# 用法:
#   bash scripts/auto_renew_seller_cookie.sh              # 探活，只有失效才重签
#   bash scripts/auto_renew_seller_cookie.sh --force      # 强制重签（换店/换机/手工兜底）
set -uo pipefail
cd "$(dirname "$0")/.."

FORCE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --force)   FORCE=1; shift ;;
    --max-age) shift 2 ;;   # 兼容旧参数，已不再按时间触发
    *) shift ;;
  esac
done

LOG="$HOME/.config/ozon-seller/autorenew.log"
mkdir -p "$(dirname "$LOG")"
log() { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }

SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"
MINT_MJS="$SCRIPTS_DIR/mint_seller_cookie.mjs"

do_mint() {
  log "-> 重签"
  local tmp rc
  tmp="$(mktemp /tmp/mint-XXXXXX.mjs)"
  printf "await import('file://%s');\n" "$MINT_MJS" > "$tmp"
  ego-browser nodejs < "$tmp" 2>&1 | grep -E '^\[mint\]' | tee -a "$LOG"
  rc=${PIPESTATUS[0]}
  rm -f "$tmp"
  if [ "$rc" -ne 0 ]; then
    log "X 重签失败 rc=$rc (ego 里卖家端是否还登着?)"
    return 6
  fi
  return 0
}

# ---- 1) 探活
PROBE_OUT="$(python3 scripts/auto_renew_probe.py 2>/dev/null)"
STATUS="$(echo "$PROBE_OUT" | cut -d' ' -f1)"
CODE="$(echo "$PROBE_OUT"   | cut -d' ' -f2)"
SINCE="$(echo "$PROBE_OUT"  | cut -d' ' -f3)"

log "探活=$STATUS code=$CODE 距上次写入=${SINCE}h"

# 重签只是**抄一份浏览器当前持有的 token**，不会让 token 变新。
# 所以只在真的不可用时才动手。
NEED=0
if [ "$FORCE" -eq 1 ]; then
  log "强制模式"; NEED=1
elif [ "$STATUS" = "FAIL" ]; then
  log "鉴权失效(401) -> 重签"; NEED=1
elif [ "$STATUS" = "AUTH" ]; then
  log "abt_data 掉(403 挑战) -> 重签"; NEED=1
elif [ "$STATUS" = "NET" ]; then
  log "网络问题，不重签"; exit 4
elif [ "$STATUS" = "THR" ]; then
  log "被限流，不是 cookie 问题"; exit 3
elif [ "$STATUS" = "ERR" ]; then
  log "jar 读取失败"; exit 2
elif [ "$STATUS" = "OK" ]; then
  log "token 可用($CODE)，无需重签"; exit 0
else
  log "未知探活状态: $PROBE_OUT"; exit 4
fi

[ "$NEED" = "1" ] || exit 0

do_mint || exit $?

# ---- 4) 复验
sleep 2
python3 scripts/keepalive_seller_cookie.py | tee -a "$LOG"
rc=${PIPESTATUS[0]}
if [ "$rc" -eq 0 ]; then log "OK 重签成功并复验通过"; else log "X 复验失败 rc=$rc"; fi
exit "$rc"
