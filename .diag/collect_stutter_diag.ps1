# collect_stutter_diag.ps1 - read-only diagnostics collection
$ErrorActionPreference = 'SilentlyContinue'
$start = (Get-Date).AddHours(-8)

Write-Output "=== [1] App Error/Hang/WER events mentioning chrome (last 8h) ==="
Get-WinEvent -FilterHashtable @{LogName='Application'; StartTime=$start; Id=1000,1001,1002} |
    Where-Object { $_.Message -match 'chrome|Chromium' } |
    ForEach-Object { "{0}  Id={1}  {2}" -f $_.TimeCreated, $_.Id, $_.ProviderName; ($_.Message -split "`n" | Select-Object -First 12) -join "`n"; "----" }

Write-Output "=== [2] Display/TDR + GPU driver events (System log, last 8h) ==="
Get-WinEvent -FilterHashtable @{LogName='System'; StartTime=$start} |
    Where-Object { $_.ProviderName -match 'nvlddmkm|igfx|igdkm|Display|Kernel-PnP' -and $_.LevelDisplayName -ne 'Information' } |
    Select-Object TimeCreated, Id, ProviderName, LevelDisplayName | Format-Table -AutoSize | Out-String -Width 200

Write-Output "=== [3] Resource Exhaustion Detector (low memory events) ==="
Get-WinEvent -FilterHashtable @{LogName='System'; StartTime=$start; ProviderName='Microsoft-Windows-Resource-Exhaustion-Detector'} |
    Select-Object TimeCreated, Id | Format-Table -AutoSize | Out-String

Write-Output "=== [4] Crashpad reports/pending ==="
Get-ChildItem "$env:LOCALAPPDATA\Chromium\User Data\Crashpad\reports", "$env:LOCALAPPDATA\Chromium\User Data\Crashpad\pending" -File |
    Sort-Object LastWriteTime -Descending | Select-Object -First 15 Name, @{N='KB';E={[math]::Round($_.Length/1KB)}}, LastWriteTime |
    Format-Table -AutoSize | Out-String

Write-Output "=== [5] WER ReportQueue chrome entries ==="
Get-ChildItem "$env:PROGRAMDATA\Microsoft\Windows\WER\ReportQueue", "$env:LOCALAPPDATA\Microsoft\Windows\WER\ReportQueue" -Directory |
    Where-Object { $_.Name -match 'chrome|Chromium' } |
    Sort-Object LastWriteTime -Descending | Select-Object -First 12 Name, LastWriteTime |
    Format-Table -AutoSize | Out-String

Write-Output "=== [6] LiveKernelReports (video TDR 0x141 etc) ==="
Get-ChildItem "C:\Windows\LiveKernelReports" -Recurse -File |
    Sort-Object LastWriteTime -Descending | Select-Object -First 8 FullName, @{N='MB';E={[math]::Round($_.Length/1MB,1)}}, LastWriteTime |
    Format-Table -AutoSize | Out-String

Write-Output "=== [7] GPUs and driver versions ==="
Get-CimInstance Win32_VideoController | Select-Object Name, DriverVersion, @{N='DriverDate';E={$_.DriverDate}}, Status, VideoProcessor |
    Format-List | Out-String

Write-Output "=== [8] chrome processes now ==="
$procs = Get-Process chrome
if ($procs) {
    $procs | Select-Object Id, @{N='MemMB';E={[math]::Round($_.WorkingSet64/1MB)}}, @{N='CPU_s';E={[math]::Round($_.CPU,1)}}, Path |
        Sort-Object MemMB -Descending | Format-Table -AutoSize | Out-String -Width 250
    "total chrome processes: {0}, total mem MB: {1}" -f $procs.Count, [math]::Round(($procs | Measure-Object WorkingSet64 -Sum).Sum/1MB)
} else { "no chrome process running" }

Write-Output "=== [9] memory / commit now ==="
$os = Get-CimInstance Win32_OperatingSystem
"FreePhysGB={0}  TotalPhysGB={1}  CommitLimitGB={2}  CommitFreeGB={3}" -f `
    [math]::Round($os.FreePhysicalMemory/1MB,1), [math]::Round($os.TotalVisibleMemorySize/1MB,1), `
    [math]::Round($os.TotalVirtualMemorySize/1MB,1), [math]::Round($os.FreeVirtualMemory/1MB,1)

Write-Output "=== [10] active build & flags file ==="
Get-Item "$env:LOCALAPPDATA\Chromium\Application\mcloud_flags.txt", "$env:LOCALAPPDATA\Chromium\Application\151.0.7922.99\mcloud_flags.txt", "D:\wxmuma\chromium-src\src\out\mcloud\mcloud_flags.txt" |
    Select-Object FullName, LastWriteTime | Format-Table -AutoSize | Out-String -Width 200
$procs | Select-Object -First 1 -ExpandProperty Path

Write-Output "=== [11] GPU process command lines (child types) ==="
Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" | ForEach-Object {
    if ($_.CommandLine -match '--type=([\w-]+)') { $Matches[1] } else { 'browser' }
} | Group-Object | Select-Object Name, Count | Format-Table -AutoSize | Out-String

Write-Output "=== [12] recent GPU/Viz related chrome switches in browser cmdline ==="
(Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" | Where-Object { $_.CommandLine -notmatch '--type=' } | Select-Object -First 1).CommandLine -split ' --' | Where-Object { $_ -match 'graphite|gpu|d3d|overlay|angle|video|features' } | Select-Object -First 10
