# =============================================================================
# MCloud Browser — 自采 PGO profile 流水线（规范 10.2）
# =============================================================================
# 目标：以真实用户场景（启动/多标签/浏览/视频）采集 profdata，替代上游通用
# profile，使 PGO 热点优化贴合产品定位。
#
# 流程：
#   phase1-build : args.gn 改 chrome_pgo_phase = 1（instrumented）后全量构建
#   collect      : 运行 instrumented 构建并驱动典型场景，产出 *.profraw
#   merge        : llvm-profdata merge 生成 pgo_data_path 指向的 .profdata
#   phase2-build : args.gn 改回 chrome_pgo_phase = 2 + 新 profdata，全量重建
#
# 前置依赖：
#   1. llvm-profdata.exe —— Chromium 内置工具链不含（已核查），须自备
#      （随 LLVM release 安装或自建 clang 时一并构建，见规范 2.5）；
#   2. phase 1/2 构建各需一次全量编译（耗时数小时），须在构建机空闲时执行。
#
# 用法：
#   .\pgo_collect.ps1 -Step phase1-build|collect|merge|phase2-build|all [-OutDir <out/mcloud>]
# =============================================================================
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("phase1-build", "collect", "merge", "phase2-build", "all")]
    [string]$Step,
    [string]$OutDir = "D:\wxmuma\chromium-src\src\out\mcloud",
    [string]$LlvmBin = "",
    [int]$CollectSeconds = 300      # 场景驱动时长
)

$ErrorActionPreference = "Stop"
$argsGn   = Join-Path $OutDir "args.gn"
$profDir  = Join-Path $OutDir "pgo_collect"
$profdata = Join-Path $profDir "mcloud-win64.profdata"

function Find-LlvmBin {
    if ($LlvmBin -and (Test-Path "$LlvmBin\llvm-profdata.exe")) { return $LlvmBin }
    $candidates = @(
        "C:\Program Files\LLVM\bin",
        "D:\wxmuma\chromium-src\src\third_party\llvm-build\Release+Asserts\bin"
    )
    foreach ($c in $candidates) {
        if (Test-Path "$c\llvm-profdata.exe") { return $c }
    }
    throw "未找到 llvm-profdata.exe（Chromium 内置工具链不含，见规范 2.5）。请安装 LLVM 工具链或用 -LlvmBin 指定。"
}

function Set-PgoPhase([int]$phase) {
    if (-not (Test-Path $argsGn)) { throw "缺少 $argsGn" }
    $content = Get-Content $argsGn -Raw
    $updated = $content -replace 'chrome_pgo_phase\s*=\s*\d', "chrome_pgo_phase = $phase"
    if ($updated -eq $content) { throw "args.gn 中未找到 chrome_pgo_phase" }
    Set-Content -Path $argsGn -Value $updated -NoNewline
    Write-Host "args.gn: chrome_pgo_phase = $phase（请重新 gn gen + 全量构建）" -ForegroundColor Yellow
}

switch ($Step) {
    "phase1-build" {
        Set-PgoPhase 1
        Write-Host "接下来执行: gn gen $OutDir --check; autoninja -C $OutDir chrome" -ForegroundColor Cyan
    }
    "collect" {
        $chromeExe = Join-Path $OutDir "chrome.exe"
        if (-not (Test-Path $chromeExe)) { throw "缺少 $chromeExe（请先完成 phase1-build）" }
        New-Item -ItemType Directory -Force -Path $profDir | Out-Null
        $env:LLVM_PROFILE_FILE = Join-Path $profDir "chrome-%p.profraw"
        Write-Host ("运行 instrumented 构建 {0}s，请模拟真实场景（多标签/浏览/视频）..." -f $CollectSeconds) -ForegroundColor Cyan
        $userDataDir = Join-Path $profDir "user-data"
        $proc = Start-Process -FilePath $chromeExe `
            -ArgumentList "--user-data-dir=$userDataDir", "--no-first-run", "about:blank" -PassThru
        Start-Sleep -Seconds $CollectSeconds
        try { $proc.Kill(); $proc.WaitForExit(15000) } catch {}
        Start-Sleep -Seconds 5
        $raws = Get-ChildItem $profDir -Filter "*.profraw"
        if (-not $raws) { throw "未产生 .profraw（确认是 phase=1 构建且 LLVM_PROFILE_FILE 可写）" }
        Write-Host ("采集到 {0} 个 .profraw（共 {1:N0} MB）" -f $raws.Count, (($raws | Measure-Object Length -Sum).Sum / 1MB)) -ForegroundColor Green
    }
    "merge" {
        $llvm = Find-LlvmBin
        $raws = Get-ChildItem $profDir -Filter "*.profraw"
        if (-not $raws) { throw "无 .profraw，请先执行 -Step collect" }
        Write-Host "llvm-profdata merge ..." -ForegroundColor Cyan
        & "$llvm\llvm-profdata.exe" merge -output=$profdata @($raws.FullName)
        if ($LASTEXITCODE -ne 0) { throw "merge 失败（exit $LASTEXITCODE）" }
        Write-Host ("完成：{0}（{1:N1} MB）" -f $profdata, ((Get-Item $profdata).Length / 1MB)) -ForegroundColor Green
        Write-Host "下一步：把 args.gn 的 pgo_data_path 指向上述 profdata，然后 -Step phase2-build"
    }
    "phase2-build" {
        Set-PgoPhase 2
        $content = Get-Content $argsGn -Raw
        $updated = $content -replace 'pgo_data_path\s*=\s*"[^"]*"', ('pgo_data_path = "' + ($profdata -replace '\\', '/') + '"')
        if ($updated -ne $content) {
            Set-Content -Path $argsGn -Value $updated -NoNewline
            Write-Host "args.gn: pgo_data_path 已指向自采 profdata" -ForegroundColor Yellow
        } else {
            Write-Warning "未自动更新 pgo_data_path，请手工指向 $profdata"
        }
        Write-Host "接下来执行: gn gen $OutDir --check; autoninja -C $OutDir chrome" -ForegroundColor Cyan
        Write-Host "构建完成后按第 7 章跑 K1-K6 对比上游 profdata 构建（规范 10.2 验证）"
    }
    "all" {
        Write-Host "all 模式为分阶段指引（中间含两次全量构建，无法无人值守串联）：" -ForegroundColor Yellow
        & $PSCommandPath -Step phase1-build -OutDir $OutDir
        Write-Host "`n[人工] 全量构建完成后 -> -Step collect -> -Step merge -> -Step phase2-build -> [人工] 再次全量构建"
    }
}
