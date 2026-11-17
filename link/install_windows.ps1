# 在 Windows 上注册开机（登录）自启的计划任务 mac-win-link，并立即启动。
# 重复运行会覆盖旧任务。卸载：Unregister-ScheduledTask -TaskName mac-win-link -Confirm:$false
$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot 'macwin_link.py'
$pythonw = (Get-Command pythonw.exe).Source

$action   = New-ScheduledTaskAction -Execute $pythonw -Argument "`"$script`" serve" -WorkingDirectory $PSScriptRoot
$trigger  = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
              -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
              -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName 'mac-win-link' -Action $action -Trigger $trigger -Settings $settings `
  -Description 'Mac 与 Windows 经 Tailscale 互联的后台服务（E:\工作区\claude工作区\mac-win\link）' -Force | Out-Null
Start-ScheduledTask -TaskName 'mac-win-link'
Write-Host "已注册并启动计划任务 mac-win-link"
