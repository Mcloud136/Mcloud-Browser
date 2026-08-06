# =============================================================================
# MCloud Browser — BOLT 后链接优化流水线（规范 10.1）
# =============================================================================
# 流程（参照 src/tools/clang/scripts/build.py 第 1651 行起的范式）：
#   instrument  : llvm-bolt 对 chrome.exe 插桩生成 chrome-bolt.inst.exe
#   collect     : 以真实负载运行插桩版，产出 perf.fdata
#   optimize    : llvm-bolt 依据 fdata 重排二进制布局 → chrome.exe.bolted
#   verify      : K1 冷启动对比后，替换正式产物
#
# 前置依赖（未就绪时脚本会明确报错）：
#   1. llvm-bolt.exe / merge-fdata.exe —— Chromium 内置工具链不含，须自备
#      （随 LLVM release 安装，或 infra/build_polly.sh 自建 clang 时一并构建）；
#   2. use_bolt = true 的构建（emit-relocs 已接线，保留重定位信息）；
#   3. Windows 无 perf，采用 instrumentation 采集（-instrument 模式）。
#
# 用法：
#   .\bolt_pipeline.ps1 -Step instrument|collect|optimize|verify|all [-OutDir <out/mcloud>]
# =============================================================================
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("instrument", "collect", "optimize", "verify", "all")]
    [string]$Step,
    [string]$OutDir = "D:\wxmuma\chromium-src\src\out\mcloud",
    [string]$LlvmBin = "",          # llvm-bolt.exe 所在目录；留空则自动探测
    [int]$CollectSeconds = 120      # 插桩版运行时长（采集窗口）
)

$ErrorActionPreference = "Stop"

function Find-LlvmBin {
    if ($LlvmBin -and (Test-Path "$LlvmBin\llvm-bolt.exe")) { return $LlvmBin }
    $candidates = @(
        "C:\Program Files\LLVM\bin",
        "D:\wxmuma\chromium-src\src\third_party\llvm-build\Release+Asserts\bin"
    )
    foreach ($c in $candidates) {
        if (Test-Path "$c\llvm-bolt.exe") { return $c }
    }
    throw "未找到 llvm-bolt.exe。请安装 LLVM 工具链或用 -LlvmBin 指定目录（Chromium 内置工具链不含 BOLT，见规范 2.5）。"
}

$chromeExe = Join-Path $OutDir "chrome.exe"
$instExe   = Join-Path $OutDir "chrome-bolt.inst.exe"
$fdata     = Join-Path $OutDir "bolt-profiles\prof.fdata"
$boltedExe = Join-Path $OutDir "chrome.exe.bolted"

switch ($Step) {
    "instrument" {
        $llvm = Find-LlvmBin
        if (-not (Test-Path $chromeExe)) { throw "缺少 $chromeExe（请先完成 use_bolt=true 的构建）" }
        Write-Host "插桩 chrome.exe ..." -ForegroundColor Cyan
        & "$llvm\llvm-bolt.exe" $chromeExe -o $instExe `
            -instrument -instrumentation-file-append-hot `
            "--instr-tools=$llvm"
        if ($LASTEXITCODE -ne 0) { throw "instrument 失败（exit $LASTEXITCODE）" }
        Write-Host "完成：$instExe" -ForegroundColor Green
    }
    "collect" {
        if (-not (Test-Path $instExe)) { throw "缺少插桩产物，请先执行 -Step instrument" }
        New-Item -ItemType Directory -Force -Path (Split-Path $fdata) | Out-Null
        Write-Host ("运行插桩版 {0}s 采集 profile（请在此期间模拟真实使用：启动/浏览/视频）..." -f $CollectSeconds) -ForegroundColor Cyan
        $env:BOLT_PROFILE_DIR = Split-Path $fdata
        $proc = Start-Process -FilePath $instExe -ArgumentList "--no-first-run", "about:blank" -PassThru
        Start-Sleep -Seconds $CollectSeconds
        try { $proc.Kill(); $proc.WaitForExit(10000) } catch {}
        Start-Sleep -Seconds 5   # 等待 profile 落盘
        $raw = Get-ChildItem (Split-Path $fdata) -Filter "*.prof*" -ErrorAction SilentlyContinue
        if (-not $raw) { throw "未采集到 profile 数据（检查 BOLT_PROFILE_DIR 输出）" }
        Write-Host ("采集到 {0} 个原始 profile 文件" -f $raw.Count) -ForegroundColor Green
        # 多文件合并（merge-fdata）
        $llvm = Find-LlvmBin
        if ($raw.Count -gt 1 -and (Test-Path "$llvm\merge-fdata.exe")) {
            $listFile = Join-Path $OutDir "bolt-profiles\files.txt"
            $raw | ForEach-Object { $_.FullName } | Out-File $listFile -Encoding ascii
            & "$llvm\merge-fdata.exe" (Get-Content $listFile) > $fdata
        } else {
            Copy-Item $raw[0].FullName $fdata -Force
        }
        Write-Host "完成：$fdata" -ForegroundColor Green
    }
    "optimize" {
        $llvm = Find-LlvmBin
        if (-not (Test-Path $fdata)) { throw "缺少 profile，请先执行 -Step collect" }
        Write-Host "BOLT 重排二进制布局 ..." -ForegroundColor Cyan
        & "$llvm\llvm-bolt.exe" $chromeExe -o $boltedExe `
            -data=$fdata `
            -reorder-blocks=ext-tsp -reorder-functions=hfsort+ `
            -split-functions -split-all-cold `
            -dyno-stats -icf=1 -use-old-text
        if ($LASTEXITCODE -ne 0) { throw "optimize 失败（exit $LASTEXITCODE）" }
        Write-Host "完成：$boltedExe" -ForegroundColor Green
        Write-Host "下一步：-Step verify 做 K1 冷启动对比，通过后替换 chrome.exe 并归档 fdata。"
    }
    "verify" {
        Write-Host "验证流程（规范 7.1 K1）：" -ForegroundColor Cyan
        Write-Host "  1. benchmark\bench_startup.ps1 对当前 chrome.exe 跑 5 次，记录中位数；"
        Write-Host "  2. 备份后以 chrome.exe.bolted 替换 chrome.exe，再跑 5 次；"
        Write-Host "  3. 提升不达预期或出现启动异常 → 还原备份（单项回退，规范 8.4）；"
        Write-Host "  4. 结果连同 fdata 版本信息归档到 docs/dev-logs/{版本}-benchmark.md。"
    }
    "all" {
        & $PSCommandPath -Step instrument -OutDir $OutDir -LlvmBin $LlvmBin
        & $PSCommandPath -Step collect -OutDir $OutDir -LlvmBin $LlvmBin -CollectSeconds $CollectSeconds
        & $PSCommandPath -Step optimize -OutDir $OutDir -LlvmBin $LlvmBin
        & $PSCommandPath -Step verify
    }
}
