# collect_stutter_diag2.ps1 - deep dive
$ErrorActionPreference = 'SilentlyContinue'
Write-Output ("now: " + (Get-Date))

Write-Output "=== [A] Kernel-PnP 219 event details (today) ==="
Get-WinEvent -FilterHashtable @{LogName='System'; StartTime=(Get-Date).Date; ProviderName='Microsoft-Windows-Kernel-PnP'} |
    ForEach-Object { "{0}  Id={1}  Level={2}" -f $_.TimeCreated, $_.Id, $_.Level; $_.Message; "----" }

Write-Output "=== [B] ALL System log Warning/Error today (grouped) ==="
Get-WinEvent -FilterHashtable @{LogName='System'; StartTime=(Get-Date).Date; Level=1,2,3} |
    Group-Object ProviderName | Sort-Object Count -Descending |
    ForEach-Object { "{0} x{1} (ids: {2})" -f $_.Name, $_.Count, (($_.Group | Select-Object -ExpandProperty Id -Unique) -join ',') }

Write-Output "=== [C] dwm / Dxgkrnl / WER events today (detail) ==="
Get-WinEvent -FilterHashtable @{LogName='System'; StartTime=(Get-Date).Date} |
    Where-Object { $_.ProviderName -match 'dwm|Dxgkrnl|WER|Kernel-Power|Kernel-Processor' } |
    ForEach-Object { "{0}  {1}  Id={2}  Lvl={3}" -f $_.TimeCreated, $_.ProviderName, $_.Id, $_.Level; ($_.Message -split "`n" | Select-Object -First 4) -join ' | '; "----" } | Select-Object -First 60

Write-Output "=== [D] Application log: anything chrome today (any id) ==="
Get-WinEvent -FilterHashtable @{LogName='Application'; StartTime=(Get-Date).Date} |
    Where-Object { $_.Message -match 'chrome' } |
    ForEach-Object { "{0}  {1}  Id={2}  Lvl={3}" -f $_.TimeCreated, $_.ProviderName, $_.Id, $_.Level; ($_.Message -split "`n" | Select-Object -First 8) -join ' | '; "----" } | Select-Object -First 40

Write-Output "=== [E] chrome process start times + types ==="
Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" | ForEach-Object {
    $type = if ($_.CommandLine -match '--type=([\w-]+)') { $Matches[1] } else { 'browser' }
    [pscustomobject]@{ PID=$_.ProcessId; Type=$type; Start=$_.CreationDate }
} | Sort-Object Start | Format-Table -AutoSize | Out-String -Width 150

Write-Output "=== [F] WER ReportArchive/LiveKernelEvents today ==="
Get-ChildItem "$env:PROGRAMDATA\Microsoft\Windows\WER\ReportArchive", "$env:PROGRAMDATA\Microsoft\Windows\WER\ReportQueue", "$env:LOCALAPPDATA\Microsoft\Windows\WER\ReportArchive", "$env:LOCALAPPDATA\Microsoft\Windows\WER\ReportQueue" -Directory |
    Where-Object { $_.LastWriteTime -gt (Get-Date).Date } |
    Select-Object Name, LastWriteTime | Format-Table -AutoSize | Out-String -Width 200

Write-Output "=== [G] display topology / active monitors ==="
Get-CimInstance -Namespace root\wmi -ClassName WmiMonitorBasicDisplayParams | Select-Object InstanceName, Active | Format-Table -AutoSize | Out-String
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Screen]::AllScreens | ForEach-Object { "{0} Primary={1} Bounds={2}" -f $_.DeviceName, $_.Primary, $_.Bounds }
