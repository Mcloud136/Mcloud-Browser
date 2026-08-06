# =============================================================================
# MCloud Browser Benchmark — K1 冷启动时间
# =============================================================================
# 用法:
#   .\bench_startup.ps1 [-ChromeExe <path>] [-Runs 5]
#
# 方法（规范 7.1 K1）:
#   每次使用全新临时用户数据目录（冷配置），启动 chrome.exe 并等待主窗口
#   初始化完成（WaitForInputIdle 作为"首屏可交互"的代理指标），记录耗时。
#   默认 5 次取中位数。运行前请关闭所有浏览器实例并尽量清空系统缓存。
# =============================================================================
param(
    [string]$ChromeExe = "D:\wxmuma\chromium-src\src\out\mcloud\chrome.exe",
    [int]$Runs = 5
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $ChromeExe)) {
    Write-Error "chrome.exe 不存在: $ChromeExe（用 -ChromeExe 指定路径）"
    exit 1
}

function Get-Median([double[]]$values) {
    $sorted = $values | Sort-Object
    $mid = [math]::Floor($sorted.Count / 2)
    if ($sorted.Count % 2) { $sorted[$mid] } else { ($sorted[$mid - 1] + $sorted[$mid]) / 2 }
}

$results = @()

for ($i = 1; $i -le $Runs; $i++) {
    $userDataDir = Join-Path $env:TEMP "mcloud_bench_k1_$PID`_$i"
    if (Test-Path $userDataDir) { Remove-Item -Recurse -Force $userDataDir }

    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $proc = Start-Process -FilePath $ChromeExe `
        -ArgumentList "--user-data-dir=$userDataDir", "--no-first-run", "--no-default-browser-check", "about:blank" `
        -PassThru

    # 等待主窗口创建与 UI 初始化（最长 60 秒超时保护）
    $ok = $proc.WaitForInputIdle(60000)
    $sw.Stop()

    if ($ok) {
        $ms = $sw.ElapsedMilliseconds
        $results += $ms
        Write-Host ("[{0}/{1}] 冷启动: {2} ms" -f $i, $Runs, $ms)
    } else {
        Write-Warning ("[{0}/{1}] 超时，丢弃本次结果" -f $i, $Runs)
    }

    # 清理进程与临时目录
    try { $proc.Kill(); $proc.WaitForExit(10000) } catch {}
    Start-Sleep -Seconds 2
    if (Test-Path $userDataDir) { Remove-Item -Recurse -Force $userDataDir }
    Start-Sleep -Seconds 3   # 让系统回到冷态
}

if ($results.Count -eq 0) {
    Write-Error "无有效结果"
    exit 1
}

$median = Get-Median $results
Write-Host ""
Write-Host ("K1 冷启动时间（{0} 次有效，中位数）: {1} ms" -f $results.Count, $median)
Write-Host "原始数据: $($results -join ', ') ms"
Write-Host "请将结果连同环境信息记录到 docs/dev-logs/（模板见 benchmark-template.md）"
