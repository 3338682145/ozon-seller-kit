#!/usr/bin/env bash
# 安装卖家端 cookie 保活定时任务（macOS LaunchAgent）
#   每 15 分钟打一次最便宜的鉴权接口，保持会话活跃 + 尽早发现吊销
# 卸载: launchctl unload ~/Library/LaunchAgents/com.puresnake.ozon-seller-keepalive.plist
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PLIST="$HOME/Library/LaunchAgents/com.puresnake.ozon-seller-keepalive.plist"
INTERVAL="${1:-900}"

mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.puresnake.ozon-seller-keepalive</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>$REPO/scripts/keepalive_seller_cookie.py</string>
  </array>
  <key>EnvironmentVariables</key><dict>
    <key>PYTHONPATH</key><string>$REPO</string>
  </dict>
  <key>StartInterval</key><integer>$INTERVAL</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$HOME/.config/ozon-seller/keepalive.log</string>
  <key>StandardErrorPath</key><string>$HOME/.config/ozon-seller/keepalive.err</string>
</dict></plist>
PLISTEOF

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "已安装: $PLIST  (每 ${INTERVAL}s 探一次)"
echo "日志:   $HOME/.config/ozon-seller/keepalive.log"
launchctl list | grep ozon-seller-keepalive || true
