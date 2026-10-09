# collect_stutter_diag3.ps1 - hybrid GPU & browser GPU state
$ErrorActionPreference = 'SilentlyContinue'

Write-Output "=== [A] Per-app GPU preference (DirectX UserGpuPreferences) ==="
$prefs = Get-ItemProperty "HKCU:\Software\Microsoft\DirectX\UserGpuPreferences"
if ($prefs) { $prefs.PSObject.Properties | Where-Object { $_.Name -notmatch '^PS' } | ForEach-Object { "{0} => {1}" -f $_.Name, $_.Value } } else { "no per-app preferences" }

Write-Output "=== [B] GPU process full command line ==="
(Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" | Where-Object { $_.CommandLine -match '--type=gpu-process' } | Select-Object -First 1).CommandLine -split ' --' | Select-Object -First 40

Write-Output "=== [C] Local State: GPU related keys ==="
$ls = Get-Content "$env:LOCALAPPDATA\Chromium\User Data\Local State" -Raw | ConvertFrom-Json
$ls.hardware_acceleration_mode | ConvertTo-Json -Depth 3
$ls.gpu | ConvertTo-Json -Depth 2 | Select-Object -First 1
Write-Output "--- local_state gpu cache info (first 600 chars) ---"
$t = Get-Content "$env:LOCALAPPDATA\Chromium\User Data\Local State" -Raw
$i = $t.IndexOf('"gpu"')
if ($i -ge 0) { $t.Substring($i, [Math]::Min(600, $t.Length - $i)) }

Write-Output "=== [D] Graphite/Dawn/shader caches in User Data (SkiaGraphite evidence) ==="
foreach ($d in @('GrShaderCache','ShaderCache','GraphiteDawnCache','DawnGraphiteCache','DawnWebGPUCache','component_crx_cache')) {
    $p = Join-Path "$env:LOCALAPPDATA\Chromium\User Data" $d
    if (Test-Path $p) {
        $s = (Get-ChildItem $p -Recurse -File | Measure-Object Length -Sum).Sum
        "{0}: {1} MB, last write {2}" -f $d, [math]::Round($s/1MB,1), (Get-Item $p).LastWriteTime
    } else { "{0}: absent" -f $d }
}

Write-Output "=== [E] which adapter renders DISPLAY1 (display config) ==="
Get-CimInstance -Namespace root\wmi -ClassName WmiMonitorConnectionParams | Select-Object InstanceName, VideoOutputTechnology | Format-Table -AutoSize | Out-String
# VideoOutputTechnology: -2147483648=INTERNAL, 0=VGA, 4=DVI, 5=HDMI, 10=DP, 2147483648=indirect/virtual

Write-Output "=== [F] NVIDIA preferred GPU setting for chrome (NV control panel profile exists?) ==="
Get-ChildItem "$env:APPDATA\NVIDIA" -Recurse -File -Filter "*.nvidia-profile*" 2>$null | Select-Object -First 3 FullName
$nvidiaSmi = "C:\Windows\System32\nvidia-smi.exe"
if (Test-Path $nvidiaSmi) { & $nvidiaSmi --query-gpu=name,driver_version,utilization.gpu,utilization.video_engine --format=csv } else { "nvidia-smi not found" }

Write-Output "=== [G] intel gpu perf counters quick (render/video engine busy not available without tools; skip) ==="
Write-Output "=== [H] recent chrome GPU data: User Data\BrowserMetrics samples ==="
Get-ChildItem "$env:LOCALAPPDATA\Chromium\User Data\BrowserMetrics" -File 2>$null | Sort-Object LastWriteTime -Descending | Select-Object -First 5 Name, LastWriteTime | Format-Table -AutoSize | Out-String
