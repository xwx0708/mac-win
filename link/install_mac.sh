#!/bin/zsh
# 在 Mac 上安装为登录自启的 LaunchAgent（com.macwin.link），崩溃会自动拉起。
# 用法：把 macwin_link.py、config.json、本脚本放到 ~/macwin-link 后运行 zsh install_mac.sh
# 卸载：launchctl bootout gui/$(id -u)/com.macwin.link && rm ~/Library/LaunchAgents/com.macwin.link.plist
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
PY="$(command -v python3 || echo /opt/homebrew/bin/python3)"
PLIST="$HOME/Library/LaunchAgents/com.macwin.link.plist"
mkdir -p "$HOME/Library/LaunchAgents" "$DIR/logs"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.macwin.link</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PY</string>
    <string>$DIR/macwin_link.py</string>
    <string>serve</string>
  </array>
  <key>WorkingDirectory</key><string>$DIR</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>StandardErrorPath</key><string>$DIR/logs/launchd.err</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/com.macwin.link" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "已安装并启动 LaunchAgent com.macwin.link（$PY）"
