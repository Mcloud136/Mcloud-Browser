# =============================================================================
# diag_igpu_green_screen.ps1 — 核显视频绿屏/花屏二分定位工具
# =============================================================================
# 用途：通过 4 组受控启动配置二分定位"核显播放视频前几秒绿屏/花屏"的故障层级。
#       详见 docs/dev-logs/ 绿屏排查记录（2026-08）。
#
# 原理：绿屏 = 显示管线读到了未初始化的 YUV/NV12 内容（U/V 为 0 时 YUV→RGB 呈绿色）。
#       三个候选层级，逐个排除：
#         T1 基线       —— 复现问题（对照组）
#         T2 禁 DComp 视频 overlay —— 命中 → DComp/MPO overlay 平面问题
#         T3 禁 D3D12 解码器（回退 D3D11）—— 命中 → D3D12 解码输出问题
#         T4 强制软件 overlay —— 命中而 T2 不中 → 硬件 overlay 平面（MPO）驱动问题
#
# 用法：
#   .\diag_igpu_green_screen.ps1                    # 交互选择 T1-T4
#   .\diag_igpu_green_screen.ps1 -Test T2           # 直接跑指定组
#   .\diag_igpu_green_screen.ps1 -ChromePath <path> # 指定浏览器路径
#
# 判定：每组用同一视频源（建议 B 站 H.264 + HEVC 各一个）播放并观察前 5 秒。
#       记录每组 3 次结果后对照上表定位层级。
# =============================================================================

param(
  [ValidateSet("T1", "T2", "T3", "T4", "ALL_INFO")]
  [string]$Test = "",
  [string]$ChromePath = "D:\wxmuma\chromium-src\src\out\mcloud\chrome.exe"
)

if (-not (Test-Path $ChromePath)) {
  Write-Host "[ERROR] chrome.exe not found: $ChromePath" -ForegroundColor Red
  Write-Host "        用 -ChromePath 指定安装版或构建产物路径。"
  exit 1
}

$chromeDir = Split-Path $ChromePath -Parent
if (-not (Test-Path (Join-Path $chromeDir "mcloud_flags.txt"))) {
  Write-Host "[WARN] $chromeDir 下无 mcloud_flags.txt，内置 66 条优化标志将不生效（不影响本诊断）。" -ForegroundColor Yellow
}

$cases = [ordered]@{
  "T1" = @{
    Desc  = "基线（默认配置，预期复现绿屏）"
    Flags = @()
  }
  "T2" = @{
    Desc  = "禁 DirectComposition 视频 overlay（视频走 GL 合成绘制）"
    Flags = @("--enable-direct-composition-video-overlays=false")
  }
  "T3" = @{
    Desc  = "禁 D3D12 视频解码器，回退 D3D11VideoDecoder"
    Flags = @("--disable-features=D3D12VideoDecoder")
  }
  "T4" = @{
    Desc  = "强制软件 overlay（绕开硬件 overlay 平面/MPO）"
    Flags = @("--disable-features=DirectCompositionSoftwareOverlays")
  }
}

function Show-GpuInfo {
  Write-Host "`n--- 本机 GPU 环境 ---" -ForegroundColor Cyan
  Get-CimInstance Win32_VideoController |
    Select-Object Name, DriverVersion | Format-Table -AutoSize
  $hs = (Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\GraphicsDrivers" -Name HwSchMode -ErrorAction SilentlyContinue).HwSchMode
  Write-Host ("硬件 GPU 调度 (HwSchMode): {0}  (2=已启用)" -f $hs)
}

function Run-Case([string]$id) {
  $c = $cases[$id]
  Write-Host "`n===== [$id] $($c.Desc) =====" -ForegroundColor Green
  $args = @("--user-data-dir=$env:TEMP\mcloud-diag-$id") + $c.Flags
  Write-Host "启动: chrome.exe $($args -join ' ')"
  Write-Host "观察要点：播放视频前 5 秒是否绿屏/花屏；chrome://media-internals 查看 Video Decoder；chrome://gpu 查看 Applied Workarounds。" -ForegroundColor Yellow
  Start-Process -FilePath $ChromePath -ArgumentList $args
}

Show-GpuInfo

if ($Test -eq "ALL_INFO") {
  Write-Host "`n仅显示环境信息，退出。"
  exit 0
}

if ($Test -eq "") {
  Write-Host "`n可选测试组："
  foreach ($k in $cases.Keys) { Write-Host ("  {0} — {1}" -f $k, $cases[$k].Desc) }
  $Test = Read-Host "输入测试组编号（T1/T2/T3/T4）"
}

if (-not $cases.Contains($Test)) {
  Write-Host "[ERROR] 未知测试组: $Test" -ForegroundColor Red
  exit 1
}

Run-Case $Test

Write-Host @"

--- 结果判读 ---
T1 复现 + T2 不复现            → DComp 视频 overlay 路径问题（首选修复：更新 Intel 驱动；
                                 或源码侧对 raptorlake + 驱动<=32.0.101.6314 加黑名单条目）
T1 复现 + T2 复现 + T3 不复现  → D3D12 解码器输出问题（修复：对该机型禁用 D3D12VideoDecoder）
T1 复现 + T4 不复现            → 硬件 overlay 平面（MPO）驱动问题（修复：更新驱动 / 注册表禁 MPO）
全部复现                       → 解码器首帧初始化问题，抓 chrome://media-internals 日志进一步分析
"@ -ForegroundColor Cyan
