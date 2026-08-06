# =============================================================================
# MCloud Browser — 导航响应速度基准（预载 feature 收益验证）
# =============================================================================
# 目的：验证预载/预连接类 feature 是否真正加快"打开页面"的响应速度。
# 方法：同一构建，对比两种模式加载同一组页面的耗时：
#   模式 A（默认）   ：内置 flags 全部生效（含预载类）
#   模式 B（禁用预载）：命令行 --disable-features 禁用预载类（加载器合并时
#                       用户条目在后，disable 优先于内置 enable）
# 流程：每种模式先用同一 profile 预热一遍 URL 列表（让预测器/预连接/缓存
#       建立状态），再测 N 轮，取中位数。
#
# 用法：
#   .\bench_navigation.ps1                 # 两种模式都测
#   .\bench_navigation.ps1 -Runs 5
# =============================================================================
param(
    [string]$ChromeExe = "D:\wxmuma\chromium-src\src\out\mcloud\chrome.exe",
    [int]$Runs = 3
)

$ErrorActionPreference = "Stop"

# 预载/预连接/预热类 feature（M151-opt 新增的启动与加载类）
$preloadFeatures = @(
    'Prerender2WarmUpCompositorForNewTabPage',
    'Prerender2WarmUpCompositorForBookmarkBar',
    'LoadingPreconnectToRedirectTarget',
    'PreloadTopChromeWebUI',
    'BookmarkTriggerForPreconnect',
    'NewTabPageTriggerForPrerender2',
    'MultipleSpareRPHs',
    'ThreadedPreloadScanner',
    'ConsumeCodeCacheOffThread',
    'InlineScriptCache',
    'PreloadSystemFonts',
    'HttpDiskCachePrewarming',
    'LCPPAutoPreconnectLcpOrigin',
    'LoadingPredictorPrefetch'
) -join ','

# 国内可直连的测试页面
$urls = @(
    'https://www.example.com',
    'https://www.bilibili.com',
    'https://www.qq.com'
)

function Get-Median([double[]]$v) {
    $s = $v | Sort-Object
    $m = [math]::Floor($s.Count / 2)
    if ($s.Count % 2) { $s[$m] } else { ($s[$m-1] + $s[$m]) / 2 }
}

function Measure-Url([string]$exe, [string]$url, [string]$profile, [string[]]$extraArgs) {
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $args = @('--headless', '--disable-gpu', "--user-data-dir=$profile",
              '--no-first-run', '--no-default-browser-check') + $extraArgs + @('--dump-dom', $url)
    & $exe @args 2>$null | Out-Null
    $sw.Stop()
    return $sw.ElapsedMilliseconds
}

function Test-Mode([string]$exe, [string]$modeName, [string[]]$extraArgs) {
    Write-Host ""
    Write-Host "===== 模式: $modeName =====" -ForegroundColor Cyan
    $profile = Join-Path $env:TEMP "mcloud_nav_$modeName"
    if (Test-Path $profile) { Remove-Item -Recurse -Force $profile }

    # 预热一遍（建立预测器/预连接/缓存状态）
    Write-Host "预热中..."
    foreach ($u in $urls) { Measure-Url $exe $u $profile $extraArgs | Out-Null }

    $results = @{}
    foreach ($u in $urls) { $results[$u] = @() }

    for ($r = 1; $r -le $Runs; $r++) {
        foreach ($u in $urls) {
            $ms = Measure-Url $exe $u $profile $extraArgs
            $results[$u] += $ms
            Write-Host ("  [{0}] {1} : {2} ms" -f $r, $u, $ms)
        }
    }

    Write-Host ""
    foreach ($u in $urls) {
        $med = Get-Median $results[$u]
        Write-Host ("  {0} 中位数: {1} ms" -f $u, $med)
    }
    Remove-Item -Recurse -Force $profile -ErrorAction SilentlyContinue
    return $results
}

if (-not (Test-Path $ChromeExe)) { Write-Error "chrome.exe 不存在: $ChromeExe"; exit 2 }

$onResults  = Test-Mode $ChromeExe "preload-on"  @()
$offResults = Test-Mode $ChromeExe "preload-off" @("--disable-features=$preloadFeatures")

Write-Host ""
Write-Host "===== 对比（preload-on vs preload-off，中位数 ms）=====" -ForegroundColor Green
foreach ($u in $urls) {
    $on  = Get-Median $onResults[$u]
    $off = Get-Median $offResults[$u]
    $delta = [math]::Round(($on - $off) / $off * 100, 1)
    Write-Host ("{0} : on={1}ms  off={2}ms  差异={3}%" -f $u, $on, $off, $delta)
}
Write-Host ""
Write-Host "说明：负值=预载更快；正值=预载更慢。单页一次性加载场景预载收益有限，"
Write-Host "预载的真实收益在重复导航/预测命中场景，此结果为下界参考。"
