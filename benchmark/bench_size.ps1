# =============================================================================
# MCloud Browser Benchmark — K7 二进制体积（仅观测记录，不作约束，规范 1.7）
# =============================================================================
# 用法:
#   .\bench_size.ps1 [-OutDir <out/mcloud 路径>]
#
# 输出：chrome.exe 体积、构建目录总体积、安装包体积（如存在）。
# =============================================================================
param(
    [string]$OutDir = "D:\wxmuma\chromium-src\src\out\mcloud"
)

$ErrorActionPreference = "Stop"

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
