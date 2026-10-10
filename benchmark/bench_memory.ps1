# =============================================================================
# MCloud Browser Benchmark — K2 内存峰值（固定标签集驻留工作集）
# =============================================================================
# 用法:
#   .\bench_memory.ps1 [-ChromeExe <path>] [-Tabs 50] [-SettleSeconds 90]
#
# 方法（规范 7.1 K2）:
#   以全新用户数据目录打开固定数量标签页，驻留稳定后对全部浏览器进程
#   的 WorkingSet64 求和。默认 50 标签、驻留 90 秒、采样 5 次取中位数。
#   默认使用 about:blank 以降低网络波动干扰；如需站点级测试可用 -UrlsFile
#   提供每行一个 URL 的文件。
# =============================================================================
param(
    [string]$ChromeExe = "D:\wxmuma\chromium-src\src\out\mcloud\chrome.exe",
    [int]$Tabs = 50,
    [int]$SettleSeconds = 90,
    [int]$Samples = 5,
    [int]$SampleInterval = 5,
    [string]$UrlsFile = "",
    [string]$ExtraFlags = ""
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $ChromeExe)) {
    Write-Error "chrome.exe 不存在: $ChromeExe（用 -ChromeExe 指定路径）"
    exit 1
}

$urls = @()
if ($UrlsFile -and (Test-Path $UrlsFile)) {
    $urls = Get-Content $UrlsFile | Where-Object { $_ -match "^https?://" }
}

$targets = @()
for ($i = 0; $i -lt $Tabs; $i++) {
    if ($urls.Count -gt 0) { $targets += $urls[$i % $urls.Count] }
    else { $targets += "about:blank" }
}

function Get-Median([double[]]$values) {
    $sorted = $values | Sort-Object
    $mid = [math]::Floor($sorted.Count / 2)
    if ($sorted.Count % 2) { $sorted[$mid] } else { ($sorted[$mid - 1] + $sorted[$mid]) / 2 }
}

$userDataDir = Join-Path $env:TEMP "mcloud_bench_k2_$PID"
if (Test-Path $userDataDir) { Remove-Item -Recurse -Force $userDataDir }

$chromeArgs = @("--user-data-dir=$userDataDir", "--no-first-run", "--no-default-browser-check")
if ($ExtraFlags) { $chromeArgs += $ExtraFlags -split '\s+' }
$chromeArgs += $targets
$proc = Start-Process -FilePath $ChromeExe -ArgumentList $chromeArgs -PassThru

Write-Host ("驻留 {0} 秒等待稳定..." -f $SettleSeconds)
Start-Sleep -Seconds $SettleSeconds

$measured = @()
$procs = @()
try {
for ($i = 1; $i -le $Samples; $i++) {
    # 缺陷 D52：旧实现按进程名汇总机器上**所有** chrome 进程（含用户自己开的浏览器、
    # 上一轮残留实例），K2 与被测实例无关。现以本次 --user-data-dir 为指纹筛选本实例 PID 树。
    $exeName = [System.IO.Path]::GetFileName($ChromeExe)
    $ids = @(Get-CimInstance Win32_Process -Filter "Name='$exeName'" |
             Where-Object { $_.CommandLine -like "*$userDataDir*" } |
             ForEach-Object { $_.ProcessId })
    if ($ids.Count -gt 0) {
        $procs = @(Get-Process -Id $ids -ErrorAction SilentlyContinue)
    } else {
        $procs = @()
    }
    $sum = ($procs | Measure-Object -Property WorkingSet64 -Sum).Sum
    $mb = [math]::Round($sum / 1MB, 1)
    $measured += $mb
    Write-Host ("[{0}/{1}] 工作集合计: {2} MB（进程数 {3}）" -f $i, $Samples, $mb, $procs.Count)
    if ($i -lt $Samples) { Start-Sleep -Seconds $SampleInterval }
}
} finally {
    # 无论采样阶段是否抛错（$ErrorActionPreference='Stop'），都必须收掉本实例进程与临时目录，
    # 否则会留下孤儿 chrome（后续测量被污染，且机器上进程越积越多）。
    if ($procs.Count -gt 0) {
        try { $null = $proc.Kill(); $null = $proc.WaitForExit(10000) } catch {}
        try { $procs | Where-Object { $_.Id -ne $proc.Id } | ForEach-Object { $_.Kill() } } catch {}
    } else {
        try { $null = $proc.Kill(); $null = $proc.WaitForExit(10000) } catch {}
    }
    Start-Sleep -Seconds 2
    if (Test-Path $userDataDir) { Remove-Item -Recurse -Force $userDataDir -ErrorAction SilentlyContinue }
}

$median = Get-Median $measured
Write-Host ""
Write-Host ("K2 内存峰值（{0} 标签驻留 {1}s，中位数）: {2} MB" -f $Tabs, $SettleSeconds, $median)
Write-Host "原始数据: $($measured -join ', ') MB"
Write-Host "请将结果连同环境信息记录到 docs/dev-logs/（模板见 benchmark-template.md）"
