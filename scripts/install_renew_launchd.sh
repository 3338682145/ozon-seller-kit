#!/usr/bin/env bash
# 安装 cookie 自动续签定时任务（每 30 分钟检查一次 token 年龄，超 5h 就换新）
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PLIST="$HOME/Library/LaunchAgents/com.puresnake.ozon-seller-renew.plist"
INTERVAL="${1:-1800}"
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.puresnake.ozon-seller-renew</string>
  <key>ProgramArguments</key><array>
    <string>/bin/bash</string>
    <string>$REPO/scripts/auto_renew_seller_cookie.sh</string>
  </array>
  <key>EnvironmentVariables</key><dict>
    <key>PATH</key><string>$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>HOME</key><string>$HOME</string>
  </dict>
  <key>StartInterval</key><integer>$INTERVAL</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$HOME/.config/ozon-seller/renew.log</string>
  <key>StandardErrorPath</key><string>$HOME/.config/ozon-seller/renew.err</string>
</dict></plist>
PLISTEOF
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "已安装: $PLIST (每 ${INTERVAL}s 检查一次)"
launchctl list | grep ozon-seller-renew || true
