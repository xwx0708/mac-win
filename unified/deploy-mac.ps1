# 把统一文件页的代码更新到 Mac（~/macwin-unified），走互联服务，不用 SSH。
# 只传内容变了的文件。页面文件（app.js / style.css / index.html）传过去后 Mac 上的页面自己刷新；
# server.js / main.js / preload.js 变了，Mac 上的 App 会自己重启一次。
# 用法：powershell -File deploy-mac.ps1
$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'
$here = $PSScriptRoot
$link = Join-Path (Split-Path $here) 'link\macwin_link.py'
$dest = '/Users/wx/macwin-unified'
$files = 'app.js', 'index.html', 'style.css', 'icon.png', 'icon.svg', 'preload.js', 'main.js', 'server.js', 'package.json', 'package-lock.json', 'mac-app.sh'
# 上次传过去的内容摘要，记在系统临时目录（丢了也没关系，就是全部重传一次）
$stamp = Join-Path $env:TEMP 'unified-deploy-mac.json'
$old = @{}
if (Test-Path $stamp) { (Get-Content $stamp -Raw | ConvertFrom-Json).psobject.Properties | ForEach-Object { $old[$_.Name] = $_.Value } }
$new = @{}; $sent = 0
foreach ($f in $files) {
  $h = (Get-FileHash (Join-Path $here $f) -Algorithm SHA1).Hash
  $new[$f] = $h
  if ($old[$f] -eq $h) { continue }
  # 页面服务的代码最后传，免得 App 重启时页面文件还是旧的
  python $link put (Join-Path $here $f) "$dest/$f"
  if ($LASTEXITCODE -ne 0) { throw "传 $f 失败" }
  $sent++
}
$new | ConvertTo-Json | Set-Content -Encoding utf8 $stamp
if ($sent -eq 0) { '没有要更新的文件' } else { "已更新 $sent 个文件" }


