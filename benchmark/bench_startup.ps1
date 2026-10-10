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
    [string]$ChromeExe = "",
    [int]$Runs = 5
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

function Get-Median([double[]]$values) {
    $sorted = $values | Sort-Object
    $mid = [math]::Floor($sorted.Count / 2)
    if ($sorted.Count % 2) { $sorted[$mid] } else { ($sorted[$mid - 1] + $sorted[$mid]) / 2 }
}

$results = @()

for ($i = 1; $i -le $Runs; $i++) {
    $userDataDir = Join-Path $env:TEMP "mcloud_bench_k1_$PID`_$i"
    if (Test-Path $userDataDir) { Remove-Item -Recurse -Force $userDataDir }

    $proc = $null
    try {
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
    } finally {
        # $ErrorActionPreference='Stop' 下任何一步抛错都必须走到这里，
        # 否则留下孤儿 chrome 与被占用的临时目录，后续轮次被污染（缺陷 D54）。
        if ($proc) {
            try { $null = $proc.Kill(); $null = $proc.WaitForExit(10000) } catch {}
            Start-Sleep -Seconds 2
        }
        if (Test-Path $userDataDir) {
            Remove-Item -Recurse -Force $userDataDir -ErrorAction SilentlyContinue
        }
        Start-Sleep -Seconds 3   # 让系统回到冷态
    }
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
