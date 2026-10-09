# collect_stutter_diag4.ps1 - virtual display software + GPU counters baseline
$ErrorActionPreference = 'SilentlyContinue'

Write-Output "=== [A] MuMu / GameViewer / emulator / streaming processes running ==="
Get-Process | Where-Object { $_.ProcessName -match 'MuMu|NemuHeadless|MuMuVMM|GameViewer|sunlogin|todesk|向日葵|NemuPlayer|aow|LdVBox|Ld9Box|dnplayer|NoxVMHandle' } |
    Select-Object Id, ProcessName, @{N='MemMB';E={[math]::Round($_.WorkingSet64/1MB)}}, StartTime | Format-Table -AutoSize | Out-String

Write-Output "=== [B] GPU engine utilization baseline (5s sample, chrome-related) ==="
$csv = typeperf "\GPU Engine(*)\Utilization Percentage" -sc 2 -si 2 2>$null | Select-Object -Skip 1
$rows = $csv | Where-Object { $_ -match 'chrome' } | ForEach-Object {
    $parts = $_ -split '","'
    if ($parts.Count -ge 2) {
        $v = ($parts[-1] -replace '"','').Trim()
        if ([double]::TryParse($v, [ref]$null) -and [double]$v -gt 0.5) { "{0} = {1}%" -f ($parts[0] -replace '"',''), $v }
    }
}
if ($rows) { $rows | Select-Object -First 25 } else { "no chrome GPU engine activity >0.5% (idle baseline)" }

Write-Output "=== [C] available GPU engine counter instances (chrome only, first 10) ==="
$inst = (Get-Counter "\GPU Engine(*)\Utilization Percentage").CounterSamples | Where-Object { $_.InstanceName -match 'chrome' } | Select-Object -First 10 -ExpandProperty InstanceName
$inst

Write-Output "=== [D] Video Decode / Render engines present? ==="
(Get-Counter "\GPU Engine(*)\Utilization Percentage").CounterSamples | ForEach-Object { $_.InstanceName } | Where-Object { $_ -match 'engtype' } | ForEach-Object { if ($_ -match 'engtype_(\w+)') { $Matches[1] } } | Group-Object | Sort-Object Count -Descending | Select-Object Name, Count | Format-Table -AutoSize | Out-String

Write-Output "=== [E] Intel driver detail ==="
Get-CimInstance Win32_PnPSignedDriver | Where-Object { $_.DeviceName -match 'Intel.*Graphics|UHD' } | Select-Object DeviceName, DriverVersion, DriverDate | Format-List | Out-String
