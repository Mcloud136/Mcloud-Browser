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
# ⚠ 测的是什么、不是测的是什么（第3周期 bug-review 的 D78 更正）：
#   本脚本走 `--headless=new --dump-dom`，量到的是**headless 进程内从启动到 dump 完成**的墙钟时间。
#   它**不含 GPU 合成/光栅化路径**（本项目已确立：headless 不能作为 GPU 渲染判据，见
#   benchmark/tools/gpu_probe.py 与缺陷 D68——M155 上 headless dump 甚至可能拿不到 DOM）。
#   因此本脚本只能用于"相对趋势"，不能声称测的是真实打开体验；要测真实渲染路径需另建
#   窗口化 + CDP 的 K3 通道（仍在 docs/tasks/m155-perf-features.md §5.2 的待办里）。
#   配套护栏：DOM 为空即判失败（不再输出"耗时"）、每次调用有超时（不再无限挂）、
#   实例级清理（不机器级杀进程）、profile 用 PID+GUID 唯一化。
#
# 用法：
#   .\bench_navigation.ps1                 # 两种模式都测
#   .\bench_navigation.ps1 -Runs 5 -TimeoutSec 60
# =============================================================================
param(
    [string]$ChromeExe = "",
    [int]$Runs = 3,
    [int]$TimeoutSec = 60
)

$ErrorActionPreference = "Stop"

# 中文输出护栏（第3周期 bug-review，缺陷 D82）：stdout 被管道/文件捕获时，PowerShell 5.1
# 按控制台代码页（本机 GBK 936）编码，日志里的中文全是乱码，人工核对极易误读。
# 显式改为无 BOM 的 UTF-8；无控制台时（如服务上下文）setter 可能抛错，故 try 包裹。
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false } catch {}

# 被测对象口径（第3周期 bug-review，缺陷 D86）：旧默认值硬编码在 M151 回滚参考树
# （chromium-src\src），不传 -ChromeExe 就会量到旧树，而日志里看不出测的是哪个二进制
# ——与 D72"给陈旧产物开绿灯"同族的归属错误。现在默认取 $env:MCHROME_EXE，退回当前
# 155 树，并打印被测对象身份（路径/大小/修改时间/内置标志是否同目录）。
if (-not $ChromeExe) { $ChromeExe = if ($env:MCHROME_EXE) { $env:MCHROME_EXE } else { 'D:\wxmuma\chromium-src-155\src\out\mcloud\chrome.exe' } }
if (-not (Test-Path $ChromeExe)) { throw "chrome.exe 不存在: $ChromeExe" }
$subject = Get-Item $ChromeExe
# D183：判据必须按加载器口径找清单（安装版在版本目录里，不在 chrome.exe 同目录）
. (Join-Path $PSScriptRoot 'tools\mcloud_flags_lookup.ps1')
$flagsProbe = Get-McloudFlagsProbe $subject
$flagsText = if ($flagsProbe.Found) { '可读到（' + $flagsProbe.Where + '）' } else { '读不到（' + $flagsProbe.Where + '，内置优化不生效，结果无意义）' }
Write-Host ("被测对象: {0} | {1:N0} B | mtime={2:s} | 内置标志文件={3} -> {4}" -f `
    $subject.FullName, $subject.Length, $subject.LastWriteTime, $flagsText, $flagsProbe.Path)
if ($subject.FullName -match 'chromium-src(\\|$)') {
    Write-Warning "被测对象位于 M151 回滚参考树，不是当前发布对象（155）。确认这是你要测的目标。"
}

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

# 缺陷 D92（第3周期实测）：Measure-Url 的 finally 里删重定向临时文件时，浏览器子进程
# （renderer / crashpad）仍持有 stdout 句柄，Remove-Item 会失败；当时用
# -ErrorAction SilentlyContinue 直接吞掉 → 两次实跑在 %TEMP% 留下 42 个 navdom_*/naverr_*
# 文件（0 B 到 400 KB 不等）。"静默继续"把资源泄漏变成了看不见的泄漏。
# 现在：失败的文件登记到 $script:pendingCleanup（注意必须用 $script:，见缺陷 D89 的作用域坑），
# 由 Test-Mode 的 finally 在**杀掉本实例进程之后**重试，最后仍删不掉就显式报数量。
$script:pendingCleanup = @()

function Remove-TempFile([string]$path) {
    if (-not (Test-Path $path)) { return $true }
    Remove-Item $path -Force -ErrorAction SilentlyContinue
    if (Test-Path $path) {
        $script:pendingCleanup += $path
        return $false
    }
    return $true
}

function Flush-PendingCleanup {
    if ($script:pendingCleanup.Count -eq 0) { return 0 }
    foreach ($f in @($script:pendingCleanup)) {
        if (Test-Path $f) { Remove-Item $f -Force -ErrorAction SilentlyContinue }
    }
    $left = @($script:pendingCleanup | Where-Object { Test-Path $_ })
    $script:pendingCleanup = @()
    return $left.Count
}

function Measure-Url([string]$exe, [string]$url, [string]$prof, [string[]]$extra) {
    # D78/D79/D80：旧实现有三处致命问题——
    #   ① `--headless`（旧模式）+ `--disable-gpu` 且用 `2>$null | Out-Null` 吞掉一切输出，
    #      即使 dump 什么都没拿到也照样报出一个"耗时"，那数字其实是进程启动+退出的墙钟；
    #   ② `& $exe` 无超时，页面卡住/网络不通时整个基准永久挂起；
    #   ③ 参数名 `$args`/`$profile` 与 PowerShell 自动变量同名，跨作用域行为不可靠。
    # 现在：显式 --headless=new、stdout 落盘并**以字节数判成功**、Start-Process + Wait 超时、
    # 局部变量改名。DOM 为空一律判失败，绝不产出可疑耗时。
    $domFile = Join-Path $env:TEMP ("navdom_{0}.html" -f [guid]::NewGuid().ToString("N"))
    $errFile = Join-Path $env:TEMP ("naverr_{0}.txt" -f [guid]::NewGuid().ToString("N"))
    $argv = @('--headless=new', '--disable-gpu', "--user-data-dir=$prof",
              '--no-first-run', '--no-default-browser-check') + $extra + @('--dump-dom', $url)
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $p = $null
    try {
        $p = Start-Process -FilePath $exe -ArgumentList $argv -NoNewWindow -PassThru `
                           -RedirectStandardOutput $domFile -RedirectStandardError $errFile
        # PS 5.1 的 [System.Diagnostics.Process] 没有 Wait(int) 重载，只有 WaitForExit(int)；
        # 写成 $p.Wait() 会抛 MethodNotFound（第3周期实测，缺陷 D81）。
        if (-not $p.WaitForExit($TimeoutSec * 1000)) {
            try { $null = $p.Kill(); $null = $p.WaitForExit(5000) } catch {}
            $sw.Stop()
            return [pscustomobject]@{ Ms = -1; Bytes = 0; TimedOut = $true }
        }
        $sw.Stop()
        $bytes = 0
        if (Test-Path $domFile) { $bytes = (Get-Item $domFile).Length }
        return [pscustomobject]@{ Ms = $sw.ElapsedMilliseconds; Bytes = $bytes; TimedOut = $false }
    } finally {
        # 先尽力删；删不掉（子进程还握着句柄）就登记待清，由 Test-Mode 在杀进程后重试（D92）
        foreach ($f in @($domFile, $errFile)) { $null = Remove-TempFile $f }
    }
}

function Test-Mode([string]$exe, [string]$modeName, [string[]]$extraArgs) {
    Write-Host ""
    Write-Host "===== 模式: $modeName =====" -ForegroundColor Cyan
    # profile 名唯一化（PID + GUID 片段）：同一台机器上并行或残留时不会互抢目录锁
    $navProf = Join-Path $env:TEMP ("mcloud_nav_{0}_{1}_{2}" -f $modeName, $PID,
                                    [guid]::NewGuid().ToString("N").Substring(0, 6))
    $results = @{}
    $bad = @()
    try {
        New-Item -ItemType Directory -Path $navProf -Force | Out-Null

        # 预热一遍（建立预测器/预连接/缓存状态）
        Write-Host "预热中..."
        foreach ($u in $urls) { Measure-Url $exe $u $navProf $extraArgs | Out-Null }

        foreach ($u in $urls) { $results[$u] = @() }

        for ($r = 1; $r -le $Runs; $r++) {
            foreach ($u in $urls) {
                $m = Measure-Url $exe $u $navProf $extraArgs
                if ($m.TimedOut) {
                    $bad += ("第 {0} 轮 {1}：超时（>{2}s）" -f $r, $u, $TimeoutSec)
                    Write-Host ("  [{0}] {1} : 超时 >{2}s" -f $r, $u, $TimeoutSec) -ForegroundColor Red
                    continue
                }
                if ($m.Bytes -lt 200) {
                    # headless dump 拿不到 DOM（D68 的同族现象）→ 这条耗时不是页面加载耗时
                    $bad += ("第 {0} 轮 {1}：DOM 仅 {2} 字节，判为未真正加载" -f $r, $u, $m.Bytes)
                    Write-Host ("  [{0}] {1} : DOM={2}B（视为失败，不记录耗时）" -f $r, $u, $m.Bytes) -ForegroundColor Red
                    continue
                }
                $results[$u] += $m.Ms
                Write-Host ("  [{0}] {1} : {2} ms（DOM {3} B）" -f $r, $u, $m.Ms, $m.Bytes)
            }
        }

        Write-Host ""
        foreach ($u in $urls) {
            if ($results[$u].Count -eq 0) {
                Write-Host ("  {0} 无有效样本" -f $u) -ForegroundColor Red
                continue
            }
            $med = Get-Median $results[$u]
            Write-Host ("  {0} 中位数: {1} ms（有效 {2}/{3}）" -f $u, $med, $results[$u].Count, $Runs)
        }
        if ($bad.Count -gt 0) {
            throw ("导航基准不可信：{0} 例无效（headless 未取到 DOM 或超时）。" -f $bad.Count)
        }
        return $results
    } finally {
        # 只清自己起的：按 profile 叶子名筛 PID，绝不做机器级 Stop-Process（D55 口径）
        $key = Split-Path $navProf -Leaf
        foreach ($try in 1..5) {
            $ids = @(Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" |
                     Where-Object { $_.CommandLine -like "*$key*" } | ForEach-Object { $_.ProcessId })
            if ($ids.Count -eq 0) { break }
            Get-Process -Id $ids -ErrorAction SilentlyContinue |
                Stop-Process -Force -ErrorAction SilentlyContinue
            Start-Sleep -Milliseconds 600      # 等句柄释放，再删临时文件（D92）
        }
        $leftover = Flush-PendingCleanup
        if ($leftover -gt 0) {
            Write-Warning ("有 {0} 个导航临时文件仍被占用，留在 %TEMP%（navdom_*/naverr_*）" -f $leftover)
        }
        Remove-Item -Recurse -Force $navProf -ErrorAction SilentlyContinue
    }
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
