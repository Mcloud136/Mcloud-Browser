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
    [string]$Version = "",
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
if ($OutDir -match 'chromium-src(\\|$)') { Write-Warning "被测路径属于 M151 回滚参考树，不是当前发布对象（155）。" }

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
if ($subject.FullName -match 'chromium-src(\\|$)') {
    Write-Warning "被测对象位于 M151 回滚参考树，不是当前发布对象（155）。确认这是你要测的目标。"
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# -Version 不再写死 "M150"（缺陷 D94）：报告标题与文件名都取这个值，写死就会把 M155 的
# 基线归档成 M150-benchmark.md。留空时从被测二进制的文件版本推导。
if (-not $Version) {
    $pv = $subject.VersionInfo.ProductVersion
    if ($pv -match '^(\d+)\.') { $Version = 'M' + [int]$Matches[1] } else { $Version = 'unknown' }
}

# D94 主问题：PowerShell 5.1 里 `Write-Host` 写的是 **information stream(6)**，
# `& 子脚本 | Tee-Object -Variable x` 抓的是**成功流**——三个子基准的输出全部走 Write-Host，
# 所以旧写法一行都抓不到（同机实测：不加 6>&1 捕获 0 行，加了 6 行）。
# 后果是生成的基线报告里「原始数据」是空的，KPI 表却写着「见原始数据」，
# 末尾还绿色打印「报告已写入」——一份看起来完整、实则没有数字的报告（假绿家族）。
# 现在：① 统一用 6>&1 捕获；② 从中抽出 KPI 数值填进表；③ 抽不到就判 FAIL 并让脚本非零退出。
function Invoke-BenchCapture([string]$ScriptPath, [hashtable]$Params) {
    $lines = @()
    try {
        $lines = @(& $ScriptPath @Params 6>&1 | ForEach-Object { [string]$_ })
    } catch {
        $lines = @("SUB-SCRIPT-ERROR: " + $_.Exception.Message)
    }
    # 捕获之后必须回显，否则人盯着控制台看时全程无输出（采集器变成了"黑箱跑到哪一步了"）
    foreach ($ln in $lines) { Write-Host $ln }
    return , $lines
}

function Get-BenchValue($lines, [string]$pattern) {
    foreach ($ln in $lines) {
        if ($ln -match $pattern) { return $Matches[1] }
    }
    return ''
}
$report = @()

$report += "# 基准测试结果 — $Version"
$report += ""
$report += "- **测试日期**：$(Get-Date -Format 'yyyy-MM-dd')"
# ⚠ Windows 的环境变量名是 COMPUTERNAME（没有下划线）。旧写法 $env:COMPUTER_NAME 恒为空，
# 报告里的「构建机」字段一直是空白——采集环境信息的那一行自己漏采了（缺陷 D94 子项）。
$report += "- **构建信息**：Chromium $Version，args.gn 模板：win_args_mcloud.gn，构建机：$env:COMPUTERNAME"
$report += "- **对照基准**：无（首次基线）"
$report += ""
$report += "## 环境信息"
$report += ""
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$os = Get-CimInstance Win32_OperatingSystem
$ram = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 1)

# 缺陷 D139：旧实现 `Get-CimInstance Win32_VideoController | Select-Object -First 1` 取的是
# WMI 枚举顺序里的**第一个**适配器。本机装了 MuMu / GameViewer 两个虚拟显示器，它们排在
# 真实显卡前面，于是每一份 KPI 基线的"GPU / 驱动"都被记成虚拟显示器（M155 基线写作
# "MuMu Virtual Display Adapter"，M150/M151 基线写作 GameViewer），GPU 类指标的环境归属
# 从建立起就是错的。现改为：只认 PCI 总线上的适配器，并把 PCI 设备号一并记下——
# 本机的 WMI Name 会被注册表 DeviceDesc 改名污染（独显实为 RTX 4070 Laptop / DEV_2860，
# Name 却报 GTX 1050 Ti），设备号才是可信身份。
$allGpu = @(Get-CimInstance Win32_VideoController)
$realGpu = @($allGpu | Where-Object { $_.PNPDeviceID -like 'PCI\*' })
$virtualGpu = @($allGpu | Where-Object { $_.PNPDeviceID -notlike 'PCI\*' })
$activeGpu = @($realGpu | Where-Object { $_.CurrentHorizontalResolution })
if ($realGpu.Count -eq 0) {
    # 取不到真实显卡就不能给基线编一个环境（AGENTS.md：取不到数据一律判 FAIL）
    throw "无法识别任何 PCI 显卡适配器，环境信息不成立；拒绝写出基线报告。"
}
$gpuLines = @()
foreach ($g in $realGpu) {
    $devId = if ($g.PNPDeviceID -match 'VEN_([0-9A-Fa-f]{4})&DEV_([0-9A-Fa-f]{4})') {
        '{0}:{1}' -f $Matches[1], $Matches[2]
    } else { 'unknown' }
    $role = if ($g.CurrentHorizontalResolution) {
        '{0}x{1}@{2}Hz 驱动显示' -f $g.CurrentHorizontalResolution, $g.CurrentVerticalResolution, $g.CurrentRefreshRate
    } else { '未驱动显示（核显/备用）' }
    $gpuLines += ('{0} [PCI {1}] / 驱动 {2} / {3}' -f $g.Name, $devId, $g.DriverVersion, $role)
}
$logicalProcs = [Environment]::ProcessorCount

$report += "| 项目 | 值 |"
$report += "|------|----|"
$report += "| CPU | $($cpu.Name) |"
$report += ("| 逻辑处理器 | {0}（物理核 {1}；两者不等说明超线程开启，相等说明 BIOS 里关闭——直接影响 CPU 类 KPI 的可比性） |" -f `
    $logicalProcs, $cpu.NumberOfCores)
$report += "| 内存 | $ram GB |"
$report += "| OS | $($os.Caption) $($os.Version) |"
foreach ($line in $gpuLines) { $report += "| GPU / 驱动 | $line |" }
if ($virtualGpu.Count -gt 0) {
    $report += ("| 已排除的虚拟显示适配器 | {0}（不参与渲染，旧版基线曾误把它们记成 GPU） |" -f `
        (($virtualGpu | ForEach-Object { $_.Name }) -join ', '))
}
if ($activeGpu.Count -eq 0) {
    $report += "| 警告 | 没有任何真实显卡报告活动显示模式，GPU 类指标（K5）归属存疑 |"
}
$report += "| 电源模式 | 请手工确认已设为高性能 |"
$report += "| 扩展 | 无（脚本使用全新用户数据目录） |"
$report += ""
$report += "## KPI 结果"
$report += ""

Write-Host "=== K1 冷启动（5 次）===" -ForegroundColor Cyan
$k1out = Invoke-BenchCapture (Join-Path $scriptDir 'bench_startup.ps1') @{ ChromeExe = $ChromeExe; Runs = 5 }
$k1 = Get-BenchValue $k1out 'K1 .*?中位数[）)]:\s*([\d.]+)\s*ms'

Write-Host "`n=== K2 内存（50 标签）===" -ForegroundColor Cyan
$k2out = Invoke-BenchCapture (Join-Path $scriptDir 'bench_memory.ps1') @{ ChromeExe = $ChromeExe; Tabs = 50; SettleSeconds = 90 }
$k2 = Get-BenchValue $k2out 'K2 .*?中位数[）)]:\s*([\d.]+)\s*MB'

Write-Host "`n=== K7 体积 ===" -ForegroundColor Cyan
$k7out = Invoke-BenchCapture (Join-Path $scriptDir 'bench_size.ps1') @{ OutDir = $OutDir }
$k7 = Get-BenchValue $k7out 'out/mcloud 总体积\s*:\s*([\d.,]+)\s*MB'
$k7exe = Get-BenchValue $k7out 'chrome\.exe\s*:\s*([\d.,]+)\s*MB'
$k7inst = Get-BenchValue $k7out 'mini_installer\s*:\s*([\d.,]+)\s*MB'

$missing = @()
if (-not $k1) { $missing += 'K1' }
if (-not $k2) { $missing += 'K2' }
if (-not $k7) { $missing += 'K7' }

$report += "| KPI | 指标 | 本次值 | 上次基线 | 判定 |"
$report += "|-----|------|--------|----------|------|"
$report += ("| K1 | 冷启动时间（中位数，ms） | {0} | — | {1} |" -f $(if ($k1) { $k1 } else { '取数失败' }), '待比对')
$report += ("| K2 | 内存峰值 50 标签（中位数，MB） | {0} | — | {1} |" -f $(if ($k2) { $k2 } else { '取数失败' }), '待比对')
$report += ("| K7 | 二进制体积（out/mcloud，MB） | {0} | — | —（仅观测） |" -f $(if ($k7) { $k7 } else { '取数失败' }))
$report += ("| K7-细分 | chrome.exe / mini_installer（MB） | {0} / {1} | — | —（仅观测） |" -f `
    $(if ($k7exe) { $k7exe } else { '—' }), $(if ($k7inst) { $k7inst } else { '—' }))

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
if ($missing.Count -gt 0) {
    $report += ("- **采数失败**：{0}（子基准未产出可解析的结果行，见下方原始数据）" -f ($missing -join ', '))
} else {
    $report += "- 三项自动化 KPI 均成功采数（K1/K2/K7 数值已填进上表）。"
}
$report += "- 被测对象：$($subject.FullName)（$($subject.Length) B，mtime $($subject.LastWriteTime.ToString('s'))）"
$report += "- 其余（待填写）"

$outFile = Join-Path $scriptDir "..\docs\dev-logs\$Version-benchmark.md"
$outFile = [System.IO.Path]::GetFullPath($outFile)
if (-not (Test-Path (Split-Path $outFile))) {
    New-Item -ItemType Directory -Force -Path (Split-Path $outFile) | Out-Null
}
$report | Out-File -FilePath $outFile -Encoding UTF8
Write-Host "`n报告已写入: $outFile" -ForegroundColor Green
if ($missing.Count -gt 0) {
    # 报告照样留下（它是取证），但退出码必须非 0：一份没有数字的基线不能算采集成功（D94）
    Write-Host ("采数失败：{0} —— 报告已写但本次基线无效" -f ($missing -join ', ')) -ForegroundColor Red
    exit 1
}
Write-Host "K3-K6 为手工流程，见 benchmark/README.md；完成后请补充到同一报告。"
