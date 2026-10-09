# analyze_e0repro.ps1
$ErrorActionPreference = 'Stop'
$d = Import-Csv 'd:\wxmuma\thorium\.diag\e0_repro.csv'
Write-Output ("rows: " + $d.Count + "  span: " + $d[0].timestamp + " -> " + $d[-1].timestamp)

Write-Output "=== Responding=False (UI freeze) samples ==="
$fr = @($d | Where-Object { $_.responding -eq 'False' })
Write-Output ("freeze samples: " + $fr.Count)
if ($fr.Count) { $fr | Select-Object timestamp, browser_cpu, gpu_cpu, dwm_cpu, renderer_cpu_sum, viddec, vidproc, eng3d, overlay, copy, gpu_ws_mb | Format-Table -AutoSize | Out-String -Width 220 }

Write-Output "=== high 3D engine (>50%) samples ==="
$hi = @($d | Where-Object { [double]$_.eng3d -gt 50 })
Write-Output ("count: " + $hi.Count)
$hi | Select-Object timestamp, responding, browser_cpu, gpu_cpu, dwm_cpu, viddec, vidproc, eng3d, overlay | Format-Table -AutoSize | Out-String -Width 220

Write-Output "=== browser_cpu spikes (>300ms/s) ==="
$bs = @($d | Where-Object { [double]$_.browser_cpu -gt 300 })
Write-Output ("count: " + $bs.Count)
$bs | Select-Object timestamp, responding, browser_cpu, gpu_cpu, dwm_cpu, eng3d, vidproc | Select-Object -First 20 | Format-Table -AutoSize | Out-String -Width 220

Write-Output "=== gpu_cpu spikes (>800ms/s) ==="
$gs = @($d | Where-Object { [double]$_.gpu_cpu -gt 800 })
Write-Output ("count: " + $gs.Count)
$gs | Select-Object timestamp, responding, browser_cpu, gpu_cpu, dwm_cpu, eng3d, vidproc, overlay | Select-Object -First 20 | Format-Table -AutoSize | Out-String -Width 220

Write-Output "=== overall stats ==="
$d | Measure-Object -Property viddec,vidproc,eng3d,overlay,copy,gpu_cpu,browser_cpu,dwm_cpu,renderer_cpu_sum -Maximum -Average |
    Select-Object Property, @{N='Avg';E={[math]::Round($_.Average,1)}}, @{N='Max';E={[math]::Round($_.Maximum,1)}} |
    Format-Table -AutoSize | Out-String
