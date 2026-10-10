# =============================================================================
# MCloud Browser — 内置启动标志生效验证（规范 4.1.1 验证方法 / 整改项 A6）
# =============================================================================
# 验证 chrome_main_delegate.cc 的 LoadMcloudPerformanceFlags() 是否把
# mcloud_flags.txt 注入了进程命令行。
#
# 原理：加载器在进程内追加开关，操作系统层面看不到浏览器自己的命令行改动，
# 但浏览器为子进程构建命令行时会把已注册的 feature override 传下去
# （base/metrics/field_trial.cc:690 → GetCommandLineFeatureOverrides()），
# 因此**子进程命令行是唯一可靠的观测通道**。
# ⚠ 旧版首选的 `--headless=new --dump-dom chrome://version` 在 M155 上已不再返回该页 DOM
#   （实测无输出），继续拿它当主路径会让门禁"看起来跑过了"其实什么都没验（缺陷 D68）。
#   现在子进程探测是主路径，headless 只在 -KeepHeadlessProbe 下作为附加诊断。
# ⚠ 统计与清理都按本次 --user-data-dir 的实例指纹来，绝不按进程名做机器级操作
#   （缺陷 D52/D55：那会读到用户自己的浏览器，甚至把它杀掉）。
#
# 用法：
#   .\verify_builtin_flags.ps1 [-ChromeExe <path>]
# 通过条件：全部代表 feature 出现在输出中（退出码 0）。
# =============================================================================
param(
    [string]$ChromeExe = ""
)
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

$ErrorActionPreference = "Stop"

# 中文输出护栏（第3周期 bug-review，缺陷 D82）：stdout 被管道/文件捕获时，PowerShell 5.1
# 按控制台代码页（本机 GBK 936）编码，日志里的中文全是乱码，人工核对极易误读。
# 显式改为无 BOM 的 UTF-8；无控制台时（如服务上下文）setter 可能抛错，故 try 包裹。
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false } catch {}

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
# 禁用侧代表项：必须出现在 --disable-features 的值里才算真被禁用（缺陷 D50 的教训）
$probeDisable = @("SkiaGraphite")
$found = 0

# 实例指纹用 GUID 命名的临时 profile；统计与清理都只认这一个指纹
$probeDir = Join-Path $env:TEMP ("mcloud_a6_{0}" -f [guid]::NewGuid().ToString("N").Substring(0, 8))
$dirKey = Split-Path $probeDir -Leaf
New-Item -ItemType Directory -Path $probeDir -Force | Out-Null
$exeLeaf = Split-Path $ChromeExe -Leaf

function Stop-A6Instance($key) {
    if (-not $key) { return }
    for ($i = 0; $i -lt 4; $i++) {
        $ids = @(Get-CimInstance Win32_Process -Filter "Name='$exeLeaf'" |
                 Where-Object { $_.CommandLine -like "*$key*" } |
                 ForEach-Object { $_.ProcessId })
        if ($ids.Count -eq 0) { return }
        Get-Process -Id $ids -ErrorAction SilentlyContinue |
            Stop-Process -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    }
}

Write-Host "启动一个实例并采集其子进程命令行 ..." -ForegroundColor Cyan
$browser = $null
try {
    $browser = Start-Process -FilePath $ChromeExe `
        -ArgumentList "--user-data-dir=$probeDir", "--no-first-run",
        "--no-default-browser-check", "about:blank" -PassThru
    Start-Sleep -Seconds 14

    $lines = @(Get-CimInstance Win32_Process -Filter "Name='$exeLeaf'" |
               Where-Object { $_.CommandLine -like "*$dirKey*" } |
               ForEach-Object { $_.CommandLine })
    if ($lines.Count -eq 0) {
        # 观测通道失效必须硬失败，不许输出"0 命中"式的假结论（同 D66 的教训）
        throw "未采集到本实例任何进程命令行（指纹或 WMI 查询失效），无法判定"
    }
    Write-Host ("  本实例进程数: {0}" -f $lines.Count) -ForegroundColor DarkGray
    $allCmd = $lines -join " "
    foreach ($f in $probe) {
        if ($allCmd -match [regex]::Escape($f)) {
            Write-Host ("  [OK] {0}" -f $f) -ForegroundColor Green
            $found++
        } else {
            Write-Host ("  [MISS] {0}" -f $f) -ForegroundColor Red
        }
    }
    # 禁用侧也要证明（清单里 --disable-features 的项要在回显里看得见）
    foreach ($f in $probeDisable) {
        if ($allCmd -match ("--disable-features=[^ ]*" + [regex]::Escape($f))) {
            Write-Host ("  [OK] 禁用生效: {0}" -f $f) -ForegroundColor Green
            $found++
        } else {
            Write-Host ("  [MISS] 禁用未生效: {0}" -f $f) -ForegroundColor Red
        }
    }
} finally {
    # 清理永远不许抛（D70：旧版裸 Remove-Item 在 lockfile 仍被占用时抛异常，
    # 而 $ErrorActionPreference='Stop' 让脚本在探测中途就退出，并留下整组孤儿进程）
    Stop-A6Instance $dirKey
    if (Test-Path $probeDir) { Remove-Item -Recurse -Force $probeDir -ErrorAction SilentlyContinue }
    if (Test-Path $probeDir) { Remove-Item -Recurse -Force $probeDir -ErrorAction SilentlyContinue }
    $leftover = @(Get-CimInstance Win32_Process -Filter "Name='$exeLeaf'" -ErrorAction SilentlyContinue |
                  Where-Object { $_.CommandLine -like "*mcloud_a6_*" })
    if ($leftover.Count -gt 0) {
        Write-Warning ("仍有 {0} 个本工具启动的实例未退出（可能锁住 out 目录，影响后续编译）" -f $leftover.Count)
        exit 1
    }
}

$probeCount = $probe.Count + $probeDisable.Count

if ($found -ge $probeCount) {
    Write-Host "`n验证通过：内置启动标志已生效（A6 闭环）。请同步记录到 docs/dev-logs/。" -ForegroundColor Green
    exit 0
} else {
    Write-Host ("`n验证未通过（{0}/{1}）。检查：① mcloud_flags.txt 是否在 exe 同目录；" -f $found, $probeCount) -ForegroundColor Yellow
    Write-Host  "  ② chrome_main_delegate.cc 是否已编进当前构建；③ v6 起加载器只在浏览器进程读文件，" -ForegroundColor Yellow
    Write-Host  "   子进程靠命令行继承下发，所以要看的是子进程命令行而不是浏览器自己的。" -ForegroundColor Yellow
    exit 1
}

