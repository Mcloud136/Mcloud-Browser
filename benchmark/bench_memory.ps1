# =============================================================================
# MCloud Browser Benchmark — K2 内存峰值（固定标签集驻留工作集）
# =============================================================================
# 用法:
#   .\bench_memory.ps1 [-ChromeExe <path>] [-Tabs 50] [-SettleSeconds 90]
#
# 方法（规范 7.1 K2）:
#   以全新用户数据目录打开固定数量标签页，驻留稳定后对全部浏览器进程
#   的 WorkingSet64 求和。默认 50 标签、驻留 90 秒、采样 5 次取中位数。
#   默认使用 about:blank 以降低网络波动干扰；如需站点级测试可用 -UrlsFile
#   提供每行一个 URL 的文件。
# =============================================================================
param(
    [string]$ChromeExe = "",
    [int]$Tabs = 50,
    [int]$SettleSeconds = 90,
    [int]$Samples = 5,
    [int]$SampleInterval = 5,
    [string]$UrlsFile = "",
    [string]$ExtraFlags = "",
    [switch]$NoCpu
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
# 旧写法 'chromium-src(\|$)' 里的 \| 是"转义竖线"，匹配字面量 "|"，任何真实路径都不含它，
# 于是这条护栏从未触发过（缺陷 D137）。正确写法是 (\\|$)：反斜杠或串尾，才能把
# chromium-src\（M151 回滚树）与 chromium-src-155\（当前发布树）区分开。
if ($subject.FullName -match 'chromium-src(\\|$)') {
    Write-Warning "被测对象位于 M151 回滚参考树，不是当前发布对象（155）。确认这是你要测的目标。"
}

if (-not (Test-Path $ChromeExe)) {
    Write-Error "chrome.exe 不存在: $ChromeExe（用 -ChromeExe 指定路径）"
    exit 1
}

$urls = @()
if ($UrlsFile -and (Test-Path $UrlsFile)) {
    $urls = Get-Content $UrlsFile | Where-Object { $_ -match "^https?://" }
}

$targets = @()
for ($i = 0; $i -lt $Tabs; $i++) {
    if ($urls.Count -gt 0) { $targets += $urls[$i % $urls.Count] }
    else { $targets += "about:blank" }
}

function Get-Median([double[]]$values) {
    $sorted = $values | Sort-Object
    $mid = [math]::Floor($sorted.Count / 2)
    if ($sorted.Count % 2) { $sorted[$mid] } else { ($sorted[$mid - 1] + $sorted[$mid]) / 2 }
}

$userDataDir = Join-Path $env:TEMP "mcloud_bench_k2_$PID"
if (Test-Path $userDataDir) { Remove-Item -Recurse -Force $userDataDir }

$chromeArgs = @("--user-data-dir=$userDataDir", "--no-first-run", "--no-default-browser-check")
if ($ExtraFlags) { $chromeArgs += $ExtraFlags -split '\s+' }
$chromeArgs += $targets
$proc = Start-Process -FilePath $ChromeExe -ArgumentList $chromeArgs -PassThru

Write-Host ("驻留 {0} 秒等待稳定..." -f $SettleSeconds)
Start-Sleep -Seconds $SettleSeconds

$measured = @()
$procs = @()
# 指纹用 profile 的**叶子名**而不是完整路径：$env:TEMP 可能是 8.3 短名形式，而 chrome
# 命令行里是长名（或反之），整批子串匹配会落空——cdp.kill_instance 与 gpu_probe 都已
# 踩过这个坑（D52 修复过程中引入的次生缺陷）。
$fingerprint = [System.IO.Path]::GetFileName($userDataDir.TrimEnd('\'))
$exeName = [System.IO.Path]::GetFileName($ChromeExe)

# --- CPU 占用采集（第5周期新增，缺陷 D145：此前仓库没有任何 CPU 占用量具）---
# 复用同一批 PID 与同一次快照，所以不额外扰动被测实例，也不引入第二套进程枚举
# （避免重犯 D52/D55 按进程名统计的错）。
# TotalProcessorTime 是**累计**值，且本实例的 PID 集合会在采样间变动（renderer 起停），
# 故按 PID 分别做差再求和；新出现的 PID 其累计值就是它自诞生以来真实消耗的 CPU。
$logicalProcs = [Environment]::ProcessorCount
$cpuByPid = @{}
$cpuPctMachine = @()   # 占整机 CPU 的百分比（0~100）
$cpuCoresUsed = @()    # 折合"烧掉几个核"（多核下可 >100%）
$prevWall = $null
if (-not $NoCpu) {
    # 基线：先把当前累计值吃掉，第一次采样才有有意义的增量
    $baseIds = @(Get-CimInstance Win32_Process -Filter "Name='$exeName'" |
                 Where-Object { $_.CommandLine -like "*$fingerprint*" } |
                 ForEach-Object { $_.ProcessId })
    if ($baseIds.Count -gt 0) {
        foreach ($p in @(Get-Process -Id $baseIds -ErrorAction SilentlyContinue)) {
            try { $cpuByPid[$p.Id] = $p.TotalProcessorTime.TotalMilliseconds } catch {}
        }
    }
    $prevWall = [DateTime]::UtcNow
}

try {
for ($i = 1; $i -le $Samples; $i++) {
    # 缺陷 D52：旧实现按进程名汇总机器上**所有** chrome 进程（含用户自己开的浏览器、
    # 上一轮残留实例），K2 与被测实例无关。现以本次 --user-data-dir 为指纹筛选本实例 PID 树。
    $ids = @(Get-CimInstance Win32_Process -Filter "Name='$exeName'" |
             Where-Object { $_.CommandLine -like "*$fingerprint*" } |
             ForEach-Object { $_.ProcessId })
    if ($ids.Count -eq 0) {
        # 缺陷 D138：旧实现在这里把 $procs 置空，Measure-Object 的 Sum 得到 $null，而
        # PowerShell 里 $null / 1MB 等于 0，于是照样 measured += 0、打印"0 MB"、最后
        # 以 0 退出 —— 浏览器根本没起来却被记成"内存峰值 0 MB"，读起来像巨大改善。
        # AGENTS.md 硬规则：取不到进程必须判 FAIL，禁止返回 0 值式的"成功"。
        throw (("K2 判 FAIL：第 {0}/{1} 次采样按指纹 '{2}' 匹配到 0 个进程（浏览器可能没起来，" +
                "或指纹与命令行里的路径形式不一致）") -f $i, $Samples, $fingerprint)
    }
    $procs = @(Get-Process -Id $ids -ErrorAction SilentlyContinue)
    if ($procs.Count -eq 0) {
        throw ("K2 判 FAIL：第 {0}/{1} 次采样拿到 {2} 个 PID，但 Get-Process 一个都取不到" -f `
               $i, $Samples, $ids.Count)
    }
    $sum = ($procs | Measure-Object -Property WorkingSet64 -Sum).Sum
    if ($null -eq $sum) {
        throw ("K2 判 FAIL：第 {0}/{1} 次采样 WorkingSet64 求和为空（计数器不可用）" -f $i, $Samples)
    }
    $mb = [math]::Round($sum / 1MB, 1)
    $measured += $mb

    $cpuNote = ""
    if (-not $NoCpu) {
        $cpuMs = 0.0
        foreach ($p in $procs) {
            try { $cur = $p.TotalProcessorTime.TotalMilliseconds }
            catch { $cur = $null }
            if ($null -eq $cur) {
                # 计数器取不到就必须判 FAIL：上游 Chromium 自己在这类地方用
                # .value_or(0.0) 把失败吞成 0（task_group_sampler.cc:125），本仓库不得照抄。
                throw ("K2-CPU 判 FAIL：第 {0}/{1} 次采样读不到 pid={2} 的 TotalProcessorTime" -f `
                       $i, $Samples, $p.Id)
            }
            $prev = 0.0
            if ($cpuByPid.ContainsKey($p.Id)) { $prev = $cpuByPid[$p.Id] }
            $cpuByPid[$p.Id] = $cur
            $delta = $cur - $prev
            if ($delta -gt 0) { $cpuMs += $delta }
        }
        $now = [DateTime]::UtcNow
        $wallMs = ($now - $prevWall).TotalMilliseconds
        $prevWall = $now
        if ($wallMs -le 0) {
            throw ("K2-CPU 判 FAIL：第 {0}/{1} 次采样的墙钟增量非正（{2} ms），无法换算 CPU 占比" -f `
                   $i, $Samples, [math]::Round($wallMs, 1))
        }
        $cores = $cpuMs / $wallMs                       # 烧掉几个核
        $pctMachine = $cores / $logicalProcs * 100.0     # 占整机百分比
        # ⚠ 这里存的就是"核数"，不要再乘 100——首版误把 $cores*100 存进来，
        # 于是"0.11% 整机"旁边印出"2.70 核"，两个数字自相矛盾（实测抓到并修正）。
        $cpuCoresUsed += [math]::Round($cores, 3)
        $cpuPctMachine += [math]::Round($pctMachine, 2)
        $cpuNote = (" | CPU {0:N1}% 整机（{1:N2} 核 / 共 {2} 逻辑核）" -f `
                    $pctMachine, $cores, $logicalProcs)
    }
    Write-Host ("[{0}/{1}] 工作集合计: {2} MB（进程数 {3}）{4}" -f `
                $i, $Samples, $mb, $procs.Count, $cpuNote)
    if ($i -lt $Samples) { Start-Sleep -Seconds $SampleInterval }
}
} finally {
    # 无论采样阶段是否抛错（$ErrorActionPreference='Stop'），都必须收掉本实例进程与临时目录，
    # 否则会留下孤儿 chrome（后续测量被污染，且机器上进程越积越多）。
    if ($procs.Count -gt 0) {
        try { $null = $proc.Kill(); $null = $proc.WaitForExit(10000) } catch {}
        try { $procs | Where-Object { $_.Id -ne $proc.Id } | ForEach-Object { $_.Kill() } } catch {}
    } else {
        try { $null = $proc.Kill(); $null = $proc.WaitForExit(10000) } catch {}
    }
    Start-Sleep -Seconds 2
    if (Test-Path $userDataDir) { Remove-Item -Recurse -Force $userDataDir -ErrorAction SilentlyContinue }
}

# 缺陷 D89 同族：聚合完必须自检条数。否则"汇总不完整"会表现成一个看起来完全正常的中位数，
# 而脚本仍以 0 退出——本仓库最严重的一次假绿就出在"门禁的门禁"上。
if ($measured.Count -ne $Samples) {
    throw ("K2 判 FAIL：预期 {0} 次采样，实际只拿到 {1} 次（{2}）" -f `
           $Samples, $measured.Count, ($measured -join ', '))
}

$median = Get-Median $measured
Write-Host ""
Write-Host ("K2 内存峰值（{0} 标签驻留 {1}s，中位数）: {2} MB" -f $Tabs, $SettleSeconds, $median)
Write-Host "原始数据: $($measured -join ', ') MB"

if (-not $NoCpu) {
    # 第一次采样的增量是相对"驻留结束后"的基线，已经排除了启动与建标签的峰值，
    # 所以这里得到的是**驻留态**的 CPU 占用（K2 的语义就是驻留稳定后测量）。
    if ($cpuPctMachine.Count -eq 0) {
        throw "K2-CPU 判 FAIL：没有任何一次成功的 CPU 采样，拒绝输出 0% 式的结论"
    }
    $cpuMedian = Get-Median $cpuPctMachine
    $cpuMax = ($cpuPctMachine | Measure-Object -Maximum).Maximum
    $coresMedian = Get-Median $cpuCoresUsed
    # 自洽断言：整机百分比与折合核数必须满足 pct == cores / 逻辑核 * 100。
    # 首版把核数错存成"单核百分比"（多乘了 100），两个数字并排印出来才被发现——
    # 这种单位错配必须让脚本自己拦住，不能靠人眼读日志。
    # ⚠ 拼接后的整串必须先括起来再 -f：PowerShell 里 -f 的优先级高于 +，
    #   写成 "A{0}" + "B{1}" -f $x,$y 只会格式化 B 那一段，A 里的占位符原样印出来。
    $expectedPct = $coresMedian / $logicalProcs * 100.0
    if ([math]::Abs($expectedPct - $cpuMedian) -gt 0.5) {
        throw (("K2-CPU 判 FAIL：单位不自洽——折合核数中位数 {0:N3} 核换算应为 {1:N2}% 整机，" +
                "但百分比中位数是 {2:N2}%（差 {3:N2}）") -f `
               $coresMedian, $expectedPct, $cpuMedian, [math]::Abs($expectedPct - $cpuMedian))
    }
    Write-Host ("K2-CPU 驻留占用（{0} 逻辑处理器）: 中位数 {1:N2}% 整机 / 峰值 {2:N2}% 整机" -f `
                $logicalProcs, $cpuMedian, $cpuMax)
    Write-Host ("           折合核数: 中位数 {0:N2} 核（多核下可 >1 核，这是浏览器该有的样子）" -f `
                $coresMedian)
    Write-Host "原始数据: $($cpuPctMachine -join ', ') %整机"
    # 判读提示：占整机百分比会被逻辑核数稀释，跨机器比较必须看"折合核数"那一项，
    # 否则 24 核机器上的同一份负载会显得比 8 核机器"轻"三倍（本机超线程关闭，24 核 24 线程）。
}
Write-Host "请将结果连同环境信息记录到 docs/dev-logs/（模板见 benchmark-template.md）"
exit 0
