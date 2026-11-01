#!/usr/bin/env bash
# 卖家端 cookie 自动续签
#
# 背景（2026-11-01 实测）：
#   `__Secure-token` 约 **8 小时**一换（token 第 6 段 ts2 就是签发时刻）。
#   浏览器会自己换新，但你导出的 jar 是**冻结快照**——到点就 401。
#   所以保活不是「心跳吊着」，而是**在到期前主动重签**。
#
# 策略：
#   1) 探活（129B 便宜探针）
#   2) token 年龄 > 阈值（默认 5h，8h 死线留 3h 余量）→ 主动重签
#   3) 探活失败 → 立即重签
#   4) 重签后复验
#
# 用法:
#   bash scripts/auto_renew_seller_cookie.sh              # 按策略判断
#   bash scripts/auto_renew_seller_cookie.sh --force      # 强制重签
#   bash scripts/auto_renew_seller_cookie.sh --max-age 4  # 超过 4 小时就换
set -uo pipefail
cd "$(dirname "$0")/.."

FORCE=0
MAXAGE=5
while [ $# -gt 0 ]; do
  case "$1" in
    --force)   FORCE=1; shift ;;
    --max-age) MAXAGE="${2:-5}"; shift 2 ;;
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

# ---- 1) 探活 + 算 token 年龄
PROBE_OUT="$(python3 scripts/auto_renew_probe.py 2>/dev/null)"
STATUS="$(echo "$PROBE_OUT" | cut -d' ' -f1)"
CODE="$(echo "$PROBE_OUT"   | cut -d' ' -f2)"
AGE="$(echo "$PROBE_OUT"    | cut -d' ' -f3)"

log "探活=$STATUS code=$CODE token_age=${AGE}h (阈值 ${MAXAGE}h)"

# 重要：重签只是**抄一份浏览器当前持有的 token**，不能让 token 变新。
# token 由浏览器按自己的节奏（约 8h）轮换。所以这里的目的是「保持同步 + 快到期时抓新的」。
NEED=0
if [ "$FORCE" -eq 1 ]; then
  log "强制模式"; NEED=1
elif [ "$STATUS" = "FAIL" ]; then
  log "鉴权失效 -> 重签"; NEED=1
elif [ "$STATUS" = "NET" ]; then
  log "网络问题，不重签"; exit 4
elif [ "$STATUS" = "ERR" ]; then
  log "jar 读取失败"; exit 2
elif [ "$STATUS" = "OK" ]; then
  # 年龄接近 8h 死线 → 去抄一份，多半浏览器已换新
  if [ "$AGE" != "None" ] && [ "$(python3 -c "print(1 if float('$AGE') > float('$MAXAGE') else 0)")" = "1" ]; then
    log "token 已 ${AGE}h（死线约 8h）-> 去同步一份新的"
  else
    log "token ${AGE}h，健康；仍然同步一次以跟上浏览器轮换"
  fi
  NEED=1     # 无论如何都同步一次：成本仅一次页面加载
fi

[ "$NEED" = "1" ] || exit 0

do_mint || exit $?

# ---- 4) 复验
sleep 2
python3 scripts/keepalive_seller_cookie.py | tee -a "$LOG"
rc=${PIPESTATUS[0]}
if [ "$rc" -eq 0 ]; then log "OK 重签成功并复验通过"; else log "X 复验失败 rc=$rc"; fi
exit "$rc"
