# 启动 Live Canvas 服务器，并在副屏用 Edge 应用窗口打开
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$port = 5511
$url = "http://localhost:$port"

# 1. 服务器没在跑就启动它
$running = $false
try { Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 1 | Out-Null; $running = $true } catch {}
if (-not $running) {
    Start-Process -FilePath 'node' -ArgumentList "`"$root\server.js`"" -WorkingDirectory $root -WindowStyle Hidden
    Start-Sleep -Milliseconds 800
}

# 2. 找副屏（第一个非主屏），找不到就用主屏
Add-Type -AssemblyName System.Windows.Forms
$screen = [System.Windows.Forms.Screen]::AllScreens | Where-Object { -not $_.Primary } | Select-Object -First 1
if (-not $screen) { $screen = [System.Windows.Forms.Screen]::PrimaryScreen }
$b = $screen.Bounds

# 3. 用独立配置打开 Edge 应用窗口
$edge = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
$profileDir = Join-Path $root '.edge-profile'
Start-Process -FilePath $edge -ArgumentList @(
    "--app=$url",
    "--user-data-dir=`"$profileDir`"",
    '--new-window',
    "--window-position=$($b.X),$($b.Y)",
    "--window-size=$($b.Width),$($b.Height)",
    '--no-first-run',
    '--no-default-browser-check'
)
# 4. 屏幕缩放会让上面的坐标偏移：用物理坐标把窗口移到目标屏并最大化
Add-Type @'
using System; using System.Runtime.InteropServices;
public class LiveCanvasWin {
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool MoveWindow(IntPtr h, int x, int y, int w, int hh, bool r);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
}
'@
[LiveCanvasWin]::SetProcessDPIAware() | Out-Null
$target = [System.Windows.Forms.Screen]::AllScreens | Where-Object { $_.DeviceName -eq $screen.DeviceName } | Select-Object -First 1
$pb = $target.Bounds
$hwnd = [IntPtr]::Zero
for ($i = 0; $i -lt 30 -and $hwnd -eq [IntPtr]::Zero; $i++) {
    Start-Sleep -Milliseconds 200
    $p = Get-Process msedge -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like '*统一文件页*' } | Select-Object -First 1
    if ($p) { $hwnd = $p.MainWindowHandle }
}
if ($hwnd -ne [IntPtr]::Zero) {
    [LiveCanvasWin]::ShowWindow($hwnd, 9) | Out-Null   # 先还原，才能移动
    [LiveCanvasWin]::MoveWindow($hwnd, $pb.X + 50, $pb.Y + 50, 800, 600, $true) | Out-Null
    [LiveCanvasWin]::ShowWindow($hwnd, 3) | Out-Null   # 在该屏最大化
}
Write-Host "已在 $($screen.DeviceName) 打开 $url"
