# monitor_stutter2.ps1 - 1Hz sampling, fixed pid typing, targeted counter paths
# Usage: powershell -File monitor_stutter2.ps1 [-Seconds 300] [-Out csv]
param(
    [int]$Seconds = 300,
    [string]$Out = "d:\wxmuma\thorium\.diag\e0_baseline2.csv"
)
$ErrorActionPreference = 'SilentlyContinue'

function Resolve-ChromePids {
    $procs = Get-CimInstance Win32_Process -Filter "Name='chrome.exe'"
    $script:browserPid = [int](($procs | Where-Object { $_.CommandLine -notmatch '--type=' } | Select-Object -First 1).ProcessId)
    $script:gpuPid = [int](($procs | Where-Object { $_.CommandLine -match '--type=gpu-process' } | Select-Object -First 1).ProcessId)
    $script:rendererPids = @($procs | Where-Object { $_.CommandLine -match '--type=renderer' } | ForEach-Object { [int]$_.ProcessId })
}
Resolve-ChromePids
Write-Output ("browser=" + $browserPid + " gpu=" + $gpuPid + " renderers=" + $rendererPids.Count)

# counter paths: engines of gpu process + browser process + dwm cpu
$enginePaths = @("\GPU Engine(pid_$gpuPid*)\Utilization Percentage", "\GPU Engine(pid_$browserPid*)\Utilization Percentage")

"timestamp,responding,browser_cpu,gpu_cpu,dwm_cpu,renderer_cpu_sum,viddec,vidproc,eng3d,overlay,copy,gpu_ws_mb" | Set-Content -Path $Out -Encoding UTF8

$prev = @{}
$sw = [System.Diagnostics.Stopwatch]::StartNew()
$samples = 0
while ($sw.Elapsed.TotalSeconds -lt $Seconds) {
    $t0 = Get-Date

    # process cpu snapshot (Get-Process is fast)
    $cpus = @{}
    $ws = 0
    foreach ($p in (Get-Process chrome, dwm)) {
        $cpus[[int]$p.Id] = $p.TotalProcessorTime.TotalMilliseconds
        if ([int]$p.Id -eq $gpuPid) { $ws = [math]::Round($p.WorkingSet64/1MB) }
    }
    function Delta([int]$id) { if ($prev.ContainsKey($id) -and $cpus.ContainsKey($id)) { return [math]::Round($cpus[$id] - $prev[$id]) } return 0 }
    $bCpu = Delta $browserPid
    $gCpu = Delta $gpuPid
    $dwmPid = [int](Get-Process dwm | Select-Object -First 1).Id
    $dCpu = Delta $dwmPid
    $rSum = 0; foreach ($rp in $rendererPids) { $rSum += (Delta $rp) }
    $prev = $cpus

    # responding
    $bp = Get-Process -Id $browserPid
    $resp = if ($bp) { $bp.Responding } else { 'NA' }

    # gpu engines (targeted)
    $sums = @{ 'videodecode'=0.0; 'videoprocessing'=0.0; '3d'=0.0; 'legacyoverlay'=0.0; 'copy'=0.0 }
    foreach ($s in (Get-Counter -Counter $enginePaths).CounterSamples) {
        if ($s.InstanceName -match 'engtype_(\w+)') {
            $et = $Matches[1]
            if ($sums.ContainsKey($et)) { $sums[$et] += $s.CookedValue }
        }
    }

    $line = "{0},{1},{2},{3},{4},{5},{6},{7},{8},{9},{10},{11}" -f `
        $t0.ToString('HH:mm:ss.fff'), $resp, $bCpu, $gCpu, $dCpu, $rSum, `
        [math]::Round($sums['videodecode'],1), [math]::Round($sums['videoprocessing'],1), [math]::Round($sums['3d'],1), `
        [math]::Round($sums['legacyoverlay'],1), [math]::Round($sums['copy'],1), $ws
    Add-Content -Path $Out -Value $line
    $samples++

    $el = ((Get-Date) - $t0).TotalMilliseconds
    if ($el -lt 1000) { Start-Sleep -Milliseconds ([int](1000 - $el)) }
}
Write-Output ("monitor done -> $Out  samples=$samples  elapsed=" + [math]::Round($sw.Elapsed.TotalSeconds) + "s")
