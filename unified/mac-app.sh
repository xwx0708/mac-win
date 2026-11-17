#!/bin/sh
# Mac：生成正式的 ~/Applications/统一文件页.app。
# 做法：复制一份 Electron.app，改掉名字、标识和图标，里面放一个只有两行的入口，去加载 ~/macwin-unified 里的代码。
# 这样程序坞、菜单栏、⌘Tab 里显示的都是"统一文件页"，图标是 icon.png。
# 代码更新（deploy-mac.ps1 推过来的）不用重新生成；只有 Electron 版本或图标变了才需要重跑。
# 用法：sh ~/macwin-unified/mac-app.sh
set -e
cd "$(dirname "$0")"
HERE="$(pwd)"
NAME="统一文件页"
APP="$HOME/Applications/$NAME.app"
SRC="node_modules/electron/dist/Electron.app"
[ -d "$SRC" ] || { echo "没有找到 $SRC，先在 $HERE 里运行 npm install"; exit 1; }

# 1. 图标：icon.png → icon.icns
SET="${TMPDIR:-/tmp}/$NAME-$$.iconset"   # 系统临时目录里的一次性目录
mkdir -p "$SET"
for s in 16 32 128 256 512; do
  sips -z $s $s icon.png --out "$SET/icon_${s}x${s}.png" >/dev/null
  d=$((s * 2)); sips -z $d $d icon.png --out "$SET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$SET" -o icon.icns

# 2. 旧的 App（包括以前用 AppleScript 做的启动器）移进废纸篓，不删除
if [ -e "$APP" ]; then mv "$APP" "$HOME/.Trash/$NAME-旧版-$(date +%Y%m%d-%H%M%S).app"; fi
mkdir -p "$HOME/Applications"
ditto "$SRC" "$APP"

# 3. 改名字、标识、图标
P="$APP/Contents/Info.plist"
PB=/usr/libexec/PlistBuddy
$PB -c "Set :CFBundleName $NAME" "$P"
$PB -c "Set :CFBundleDisplayName $NAME" "$P" 2>/dev/null || $PB -c "Add :CFBundleDisplayName string $NAME" "$P"
$PB -c "Set :CFBundleIdentifier com.macwin.unified" "$P"
cp icon.icns "$APP/Contents/Resources/electron.icns"

# 4. 入口：Electron 启动时会自动加载 Resources/app 里的程序，这里转去加载 ~/macwin-unified/main.js
#    productName 和项目里的一致，配置目录（单实例锁、标签等本地存储）沿用原来的
mkdir -p "$APP/Contents/Resources/app"
cat > "$APP/Contents/Resources/app/package.json" <<EOF
{ "name": "unified-files", "productName": "$NAME", "main": "index.js" }
EOF
cat > "$APP/Contents/Resources/app/index.js" <<EOF
// 统一文件页的代码在 $HERE（由 Windows 那边用 deploy-mac.ps1 更新），这里只负责转过去
require('$HERE/main.js');
EOF

# 5. 改过的程序包要重新签名（本机自签），不然 macOS 不让运行
codesign --force --deep --sign - "$APP"
touch "$APP"
echo "已生成：$APP"
