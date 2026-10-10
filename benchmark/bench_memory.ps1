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
    [string]$ChromeExe = "",
    [int]$Tabs = 50,
    [int]$SettleSeconds = 90,
    [int]$Samples = 5,
    [int]$SampleInterval = 5,
    [string]$UrlsFile = "",
    [string]$ExtraFlags = ""
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
$mcloudFlagsNextTo = Join-Path $subject.DirectoryName 'mcloud_flags.txt'
Write-Host ("被测对象: {0} | {1:N0} B | mtime={2:s} | 内置标志文件={3}" -f `
    $subject.FullName, $subject.Length, $subject.LastWriteTime,
    $(if (Test-Path $mcloudFlagsNextTo) { '同目录存在' } else { '缺失（内置优化不生效，结果无意义）' }))
if ($subject.FullName -match 'chromium-src(\|$)') {
    Write-Warning "被测对象位于 M151 回滚参考树，不是当前发布对象（155）。确认这是你要测的目标。"
}

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
