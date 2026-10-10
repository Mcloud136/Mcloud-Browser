# =============================================================================
# MCloud Browser Benchmark — K7 二进制体积（仅观测记录，不作约束，规范 1.7）
# =============================================================================
# 用法:
#   .\bench_size.ps1 [-OutDir <out/mcloud 路径>]
#
# 输出：chrome.exe 体积、构建目录总体积、安装包体积（如存在）。
# =============================================================================
param(
    [string]$OutDir = ""
)

$ErrorActionPreference = "Stop"

# 中文输出护栏（第3周期 bug-review，缺陷 D82）：stdout 被管道/文件捕获时，PowerShell 5.1
# 按控制台代码页（本机 GBK 936）编码，日志里的中文全是乱码，人工核对极易误读。
# 显式改为无 BOM 的 UTF-8；无控制台时（如服务上下文）setter 可能抛错，故 try 包裹。
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false } catch {}

# 被测对象口径（第3周期 bug-review，缺陷 D86）：默认值曾硬编码在 M151 回滚树，
# 不传 -OutDir 就量旧产物。现在默认取 $env:MCHROME_OUT（再退回当前 155 树）并打印身份。
if (-not $OutDir) { $OutDir = if ($env:MCHROME_OUT) { $env:MCHROME_OUT } else { 'D:\wxmuma\chromium-src-155\src\out\mcloud' } }
if (-not (Test-Path $OutDir)) { throw "构建目录不存在: $OutDir" }
$dll = Join-Path $OutDir 'chrome.dll'
Write-Host ("被测产物目录: {0} | chrome.dll={1} | mtime={2:s}" -f `
    $OutDir, $(if (Test-Path $dll) { '{0:N0} B' -f (Get-Item $dll).Length } else { '缺失' }),
    $(if (Test-Path $dll) { (Get-Item $dll).LastWriteTime } else { [datetime]::MinValue }))
if ($OutDir -match 'chromium-src(\|$)') {
    Write-Warning "被测目录属于 M151 回滚参考树，不是当前发布对象（155）。"
}

if (-not (Test-Path $OutDir)) {
    Write-Error "构建目录不存在: $OutDir"
    exit 1
}

function Format-Size([long]$bytes) {
    "{0:N2} MB" -f ($bytes / 1MB)
}

$chromeExe = Join-Path $OutDir "chrome.exe"
if (Test-Path $chromeExe) {
    Write-Host ("chrome.exe          : {0}" -f (Format-Size (Get-Item $chromeExe).Length))
} else {
    Write-Warning "未找到 chrome.exe（可能尚未构建或路径不同）"
}

# 安装包（mini_installer）
$installer = Get-ChildItem -Path $OutDir -Filter "*mini_installer*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($installer) {
    Write-Host ("mini_installer      : {0}  ({1})" -f (Format-Size $installer.Length), $installer.Name)
}

# 构建目录总体积（排除 obj 中间产物可选；此处统计全目录）
$total = (Get-ChildItem -Path $OutDir -Recurse -File -ErrorAction SilentlyContinue |
          Measure-Object -Property Length -Sum).Sum
Write-Host ("out/mcloud 总体积   : {0}" -f (Format-Size $total))

Write-Host ""
Write-Host "提示：体积仅为观测指标（规范 1.7），记录到 docs/dev-logs/ 即可，不设上限。"
