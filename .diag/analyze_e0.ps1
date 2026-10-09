# analyze_e0.ps1
$ErrorActionPreference = 'Stop'
$d = Import-Csv 'd:\wxmuma\thorium\.diag\e0_baseline.csv'
Write-Output ("rows: " + $d.Count + "  span: " + $d[0].timestamp + " -> " + $d[-1].timestamp)

Write-Output "=== Responding=False periods (UI freeze) ==="
$freeze = @($d | Where-Object { $_.browser_responding -eq 'False' })
if ($freeze.Count) {
    $freeze | Select-Object timestamp, browser_cpu_ms, gpu_cpu_ms, gpu_ws_mb, viddec_pct, vidproc_pct, render3d_pct, overlay_pct, copy_pct, top_renderer_pid, top_renderer_cpu_ms | Format-Table -AutoSize | Out-String -Width 220
} else { Write-Output "NO freeze captured (Responding always True)" }

Write-Output "=== samples with high engine activity (3d/overlay/vidproc > 30%) ==="
$hi = @($d | Where-Object { [double]$_.render3d_pct -gt 30 -or [double]$_.overlay_pct -gt 30 -or [double]$_.vidproc_pct -gt 30 })
Write-Output ("count: " + $hi.Count)
$hi | Select-Object timestamp, browser_cpu_ms, gpu_cpu_ms, viddec_pct, vidproc_pct, render3d_pct, overlay_pct, copy_pct | Format-Table -AutoSize | Out-String -Width 220

Write-Output "=== samples with browser_cpu_ms > 500 (UI thread busy) ==="
$busy = @($d | Where-Object { [double]$_.browser_cpu_ms -gt 500 })
Write-Output ("count: " + $busy.Count)
$busy | Select-Object timestamp, browser_cpu_ms, gpu_cpu_ms, viddec_pct, vidproc_pct, render3d_pct, overlay_pct | Format-Table -AutoSize | Out-String -Width 220

Write-Output "=== summary stats (avg/max) ==="
$d | Measure-Object -Property viddec_pct,vidproc_pct,render3d_pct,overlay_pct,copy_pct,gpu_cpu_ms,browser_cpu_ms -Maximum -Average |
    Select-Object Property, @{N='Avg';E={[math]::Round($_.Average,1)}}, @{N='Max';E={[math]::Round($_.Maximum,1)}} |
    Format-Table -AutoSize | Out-String

Write-Output "=== video decode active at all? (viddec>1 samples) ==="
@($d | Where-Object { [double]$_.viddec_pct -gt 1 }).Count
