# monitor_stutter.ps1 - sample chrome processes + GPU engines + Responding state every 1s
# Usage: powershell -File monitor_stutter.ps1 [-Seconds 180] [-Out csv-path]
param(
    [int]$Seconds = 180,
    [string]$Out = "d:\wxmuma\thorium\.diag\stutter_monitor.csv"
)
$ErrorActionPreference = 'SilentlyContinue'

"timestamp,browser_pid,browser_responding,browser_cpu_ms,gpu_pid,gpu_cpu_ms,gpu_ws_mb,viddec_pct,vidproc_pct,render3d_pct,overlay_pct,copy_pct,top_renderer_pid,top_renderer_cpu_ms" | Set-Content -Path $Out -Encoding UTF8

$sw = [System.Diagnostics.Stopwatch]::StartNew()
$prevCpu = @{}
while ($sw.Elapsed.TotalSeconds -lt $Seconds) {
    $t0 = Get-Date
    $procs = Get-CimInstance Win32_Process -Filter "Name='chrome.exe'"
    $browserPid = ($procs | Where-Object { $_.CommandLine -notmatch '--type=' } | Select-Object -First 1).ProcessId
    $gpuPid     = ($procs | Where-Object { $_.CommandLine -match '--type=gpu-process' } | Select-Object -First 1).ProcessId

    # responding state of main window
    $bproc = Get-Process -Id $browserPid
    $responding = if ($bproc) { $bproc.Responding } else { $null }

    # cpu deltas (ms/s)
    $cpuNow = @{}
    foreach ($p in (Get-Process chrome)) { $cpuNow[$p.Id] = $p.TotalProcessorTime.TotalMilliseconds }
    $bDelta = if ($prevCpu.ContainsKey($browserPid)) { [math]::Round($cpuNow[$browserPid] - $prevCpu[$browserPid]) } else { 0 }
    $gDelta = if ($gpuPid -and $prevCpu.ContainsKey($gpuPid)) { [math]::Round($cpuNow[$gpuPid] - $prevCpu[$gpuPid]) } else { 0 }
    # top renderer by cpu delta
    $topR = $null; $topRDelta = 0
    foreach ($kv in $cpuNow.GetEnumerator()) {
        if ($prevCpu.ContainsKey($kv.Key)) {
            $d = $kv.Value - $prevCpu[$kv.Key]
            if ($d -gt $topRDelta -and $kv.Key -ne $browserPid -and $kv.Key -ne $gpuPid) { $topRDelta = $d; $topR = $kv.Key }
        }
    }
    $prevCpu = $cpuNow
    $gpuWs = if ($gpuPid) { [math]::Round((Get-Process -Id $gpuPid).WorkingSet64/1MB) } else { 0 }

    # GPU engine utilization by engine type (both adapters)
    $sums = @{ 'videodecode'=0.0; 'videoprocessing'=0.0; '3d'=0.0; 'legacyoverlay'=0.0; 'copy'=0.0 }
    $samples = (Get-Counter "\GPU Engine(*)\Utilization Percentage").CounterSamples
    foreach ($s in $samples) {
        if ($s.InstanceName -match 'engtype_(\w+)' ) {
            $et = $Matches[1]
            if ($sums.ContainsKey($et)) { $sums[$et] += $s.CookedValue }
        }
    }

    $line = "{0},{1},{2},{3},{4},{5},{6},{7},{8},{9},{10},{11},{12},{13}" -f `
        $t0.ToString('HH:mm:ss.fff'), $browserPid, $responding, $bDelta, $gpuPid, $gDelta, $gpuWs, `
        [math]::Round($sums['videodecode'],1), [math]::Round($sums['videoprocessing'],1), [math]::Round($sums['3d'],1), `
        [math]::Round($sums['legacyoverlay'],1), [math]::Round($sums['copy'],1), $topR, [math]::Round($topRDelta)
    Add-Content -Path $Out -Value $line

    $elapsed = ((Get-Date) - $t0).TotalMilliseconds
    if ($elapsed -lt 1000) { Start-Sleep -Milliseconds ([int](1000 - $elapsed)) }
}
Write-Output "monitor done -> $Out"
