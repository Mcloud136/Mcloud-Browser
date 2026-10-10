# =============================================================================
# MCloud Browser Benchmark — 一键采集 K1/K2/K7 基线
# =============================================================================
# 用法:
#   .\run_baseline.ps1 [-Version M150] [-ChromeExe <path>] [-OutDir <path>]
#
# 依次执行 K1 冷启动、K2 内存、K7 体积三项自动化基准，并将结果按
# docs/dev-logs/benchmark-template.md 结构输出，可直接复制到归档文件
# docs/dev-logs/{版本}-benchmark.md。
# =============================================================================
param(
    [string]$Version = "M150",
    [string]$ChromeExe = "",
    [string]$OutDir = ""
)

$ErrorActionPreference = "Stop"

# 中文输出护栏（第3周期 bug-review，缺陷 D82）：stdout 被管道/文件捕获时，PowerShell 5.1
# 按控制台代码页（本机 GBK 936）编码，日志里的中文全是乱码，人工核对极易误读。
# 显式改为无 BOM 的 UTF-8；无控制台时（如服务上下文）setter 可能抛错，故 try 包裹。
# ⚠ 护栏必须排在所有中文 Write-Host 之前——身份横幅本身就是要看的那一行。
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false } catch {}

# 被测对象口径（第3周期 bug-review，缺陷 D86）：默认值曾硬编码为 M151 回滚参考树，
# 不显式传参就会把结果归属到错误的产物树。现在默认取 $env:MCHROME_OUT，退回当前 155 树。
if (-not $OutDir) { $OutDir = if ($env:MCHROME_OUT) { $env:MCHROME_OUT } else { 'D:\wxmuma\chromium-src-155\src\out\mcloud' } }
if ($OutDir -match 'chromium-src(\|$)') { Write-Warning "被测路径属于 M151 回滚参考树，不是当前发布对象（155）。" }

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

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$report = @()

$report += "# 基准测试结果 — $Version"
$report += ""
$report += "- **测试日期**：$(Get-Date -Format 'yyyy-MM-dd')"
$report += "- **构建信息**：Chromium $Version，args.gn 模板：win_args_mcloud.gn，构建机：$env:COMPUTER_NAME"
$report += "- **对照基准**：无（首次基线）"
$report += ""
$report += "## 环境信息"
$report += ""
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$os = Get-CimInstance Win32_OperatingSystem
$gpu = Get-CimInstance Win32_VideoController | Select-Object -First 1
$ram = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 1)
$report += "| 项目 | 值 |"
$report += "|------|----|"
$report += "| CPU | $($cpu.Name) |"
$report += "| 内存 | $ram GB |"
$report += "| OS | $($os.Caption) $($os.Version) |"
$report += "| GPU / 驱动 | $($gpu.Name) / $($gpu.DriverVersion) |"
$report += "| 电源模式 | 请手工确认已设为高性能 |"
$report += "| 扩展 | 无（脚本使用全新用户数据目录） |"
$report += ""
$report += "## KPI 结果"
$report += ""

Write-Host "=== K1 冷启动（5 次）===" -ForegroundColor Cyan
& "$scriptDir\bench_startup.ps1" -ChromeExe $ChromeExe -Runs 5 | Tee-Object -Variable k1out
$report += "| K1 | 冷启动时间（中位数，ms） | 见原始数据 | — | — |"

Write-Host "`n=== K2 内存（50 标签）===" -ForegroundColor Cyan
& "$scriptDir\bench_memory.ps1" -ChromeExe $ChromeExe -Tabs 50 -SettleSeconds 90 | Tee-Object -Variable k2out
$report += "| K2 | 内存峰值 50 标签（中位数，MB） | 见原始数据 | — | — |"

Write-Host "`n=== K7 体积 ===" -ForegroundColor Cyan
& "$scriptDir\bench_size.ps1" -OutDir $OutDir | Tee-Object -Variable k7out
$report += "| K7 | 二进制体积 | 见原始数据 | —（仅观测） | — |"

$report += ""
$report += "## 原始数据"
$report += ""
$report += '```'
$report += "--- K1 ---"; $report += $k1out
$report += "--- K2 ---"; $report += $k2out
$report += "--- K7 ---"; $report += $k7out
$report += '```'
$report += ""
$report += "## 结论与异常记录"
$report += ""
$report += "（待填写）"

$outFile = Join-Path $scriptDir "..\docs\dev-logs\$Version-benchmark.md"
$outFile = [System.IO.Path]::GetFullPath($outFile)
if (-not (Test-Path (Split-Path $outFile))) {
    New-Item -ItemType Directory -Force -Path (Split-Path $outFile) | Out-Null
}
$report | Out-File -FilePath $outFile -Encoding UTF8
Write-Host "`n报告已写入: $outFile" -ForegroundColor Green
Write-Host "K3-K6 为手工流程，见 benchmark/README.md；完成后请补充到同一报告。"
