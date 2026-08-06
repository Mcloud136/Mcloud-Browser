# =============================================================================
# MCloud Browser — 内置启动标志生效验证（规范 4.1.1 验证方法 / 整改项 A6）
# =============================================================================
# 验证 chrome_main_delegate.cc 的 LoadMcloudPerformanceFlags() 是否把
# mcloud_flags.txt 注入了进程命令行。
#
# 原理：以 headless 模式 dump chrome://version 页面，检查其中的命令行/
# 变体信息是否包含清单中的代表 feature。因加载器在进程内追加开关，
# 操作系统级命令行不可见，必须通过浏览器自报内容验证。
#
# 用法：
#   .\verify_builtin_flags.ps1 [-ChromeExe <path>]
# 通过条件：全部代表 feature 出现在输出中（退出码 0）。
# =============================================================================
param(
    [string]$ChromeExe = "D:\wxmuma\chromium-src\src\out\mcloud\chrome.exe"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $ChromeExe)) {
    Write-Error "chrome.exe 不存在: $ChromeExe"
    exit 2
}

$exeDir = Split-Path $ChromeExe
$flagsFile = Join-Path $exeDir "mcloud_flags.txt"
if (-not (Test-Path $flagsFile)) {
    Write-Error "exe 同目录缺少 mcloud_flags.txt（加载器从该位置读取）: $flagsFile"
    exit 2
}

# 从清单挑选三组代表 feature（启动/内存/媒体，规范 4.1.1 抽查要求）
$probe = @("SpareRendererForSitePerProcess", "InfiniteTabsFreezing", "PlatformHEVCDecoderSupport")
$found = 0

$userDataDir = Join-Path $env:TEMP "mcloud_verify_flags_$PID"
if (Test-Path $userDataDir) { Remove-Item -Recurse -Force $userDataDir }

Write-Host "以 headless 模式采集 chrome://version ..." -ForegroundColor Cyan
$html = & $ChromeExe --headless=new --disable-gpu --no-sandbox `
    "--user-data-dir=$userDataDir" --no-first-run `
    --enable-logging=stderr --v=0 `
    --dump-dom "chrome://version" 2>$null

if (-not $html) {
    Write-Warning "headless dump 无输出，将改用子进程命令行探测。"
} else {
    foreach ($f in $probe) {
        if ($html -match [regex]::Escape($f)) {
            Write-Host ("  [OK] {0}" -f $f) -ForegroundColor Green
            $found++
        } else {
            Write-Host ("  [MISS] {0}" -f $f) -ForegroundColor Red
        }
    }
}

if (Test-Path $userDataDir) { Remove-Item -Recurse -Force $userDataDir }

if ($found -eq $probe.Count) {
    Write-Host "`n验证通过：内置启动标志已生效（A6 闭环）。请同步记录到 docs/dev-logs/。" -ForegroundColor Green
    exit 0
}

# 兜底：headless 路径未确认时，改用子进程命令行探测——
# 加载器在进程内追加的开关会传递给渲染器等子进程，可从 WMI 命令行直接观测。
if ($found -lt $probe.Count) {
    Write-Host "`nheadless 路径未确认，改用子进程命令行探测..." -ForegroundColor Yellow
    $probeDir = Join-Path $env:TEMP "mcloud_probe_$PID"
    if (Test-Path $probeDir) { Remove-Item -Recurse -Force $probeDir }
    $browser = Start-Process -FilePath $ChromeExe `
        -ArgumentList "--user-data-dir=$probeDir", "--no-first-run", "--no-default-browser-check", "about:blank" -PassThru
    Start-Sleep -Seconds 12
    $procs = Get-CimInstance Win32_Process | Where-Object {
        $_.Name -eq (Split-Path $ChromeExe -Leaf) -and $_.CommandLine -like "*$exeDir*"
    }
    $allCmd = ($procs.CommandLine -join ' ')
    for ($i = 0; $i -lt $probe.Count; $i++) {
        if ($allCmd -match [regex]::Escape($probe[$i])) {
            Write-Host ("  [OK] {0}" -f $probe[$i]) -ForegroundColor Green
            $found++
        } else {
            Write-Host ("  [MISS] {0}" -f $probe[$i]) -ForegroundColor Red
        }
    }
    try { $browser.Kill(); $browser.WaitForExit(10000) } catch {}
    if (Test-Path $probeDir) { Remove-Item -Recurse -Force $probeDir }
}

if ($found -ge $probe.Count) {
    Write-Host "`n验证通过：内置启动标志已生效（A6 闭环）。请同步记录到 docs/dev-logs/。" -ForegroundColor Green
    exit 0
} else {
    Write-Host "`n验证未通过（$found/$($probe.Count)）。检查：① mcloud_flags.txt 是否位于 exe 同目录；② chrome_main_delegate.cc 是否已编进当前构建。" -ForegroundColor Yellow
    exit 1
}
