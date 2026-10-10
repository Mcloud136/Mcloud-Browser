# final_gate_matrix.ps1 - 收口门禁矩阵：一条命令跑完全部验证并给出每项 PASS/FAIL
# 由第3周期 bug-review 固化而来（原 .bugreview/cycle3_final_gate.ps1）。默认针对 M155 构建树，
# 可用环境变量 LOADER_TEST_OUT / 参数 -OutDir 换目标树；任何一项 FAIL 都以非零码退出。
# 用法：构建链跑完后执行；任何一项 FAIL 都以非零码退出。
# ⚠ param 必须是脚本的第一条语句（前面只能有注释/空行）。写在赋值语句之后时，PowerShell
#   不会报语法错误，而是把 `param` 当成命令名抛 CommandNotFoundException（非终止错误），
#   参数块整体作废：-OutDir 被静默丢弃、恒用默认树，且因 ErrorActionPreference='Continue'
#   仍返回退出码 0（第3周期实测，缺陷 D83）。
param([string]$OutDir = '')
$ErrorActionPreference = 'Continue'

# 中文输出护栏（第3周期 bug-review，缺陷 D82）：stdout 被管道/文件捕获时，PowerShell 5.1
# 按控制台代码页（本机 GBK 936）编码，日志里的中文全是乱码，人工核对极易误读。
# 显式改为无 BOM 的 UTF-8；无控制台时（如服务上下文）setter 可能抛错，故 try 包裹。
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false } catch {}
$LOG = 'D:\wxmuma\thorium\.bugreview\cycle3_final_gate.log'
Set-Content -LiteralPath $LOG -Value ("[{0}] === 收口门禁开始 ===" -f (Get-Date -Format 's')) -Encoding UTF8
function L($m) { Add-Content -LiteralPath $LOG -Value ("[{0}] {1}" -f (Get-Date -Format 's'), $m) -Encoding UTF8 }
$PY = 'C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe'
if (-not $OutDir) { $OutDir = 'D:\wxmuma\chromium-src-155\src\out\mcloud' }
$env:LOADER_TEST_OUT = $OutDir
$env:PYTHONUTF8 = '1'
Set-Location 'D:\wxmuma\thorium'

# ⚠ 缺陷 D89（第3周期实测）：这里原先写 `$results += ...`。PowerShell 的作用域规则是
#   "读父作用域、写即建本地副本"，函数内的 `+=` 只累加到 Invoke-Gate 的局部变量，脚本级
#   $results 永远为空 → 汇总行一行都不打印、`$bad.Count -eq 0` 恒成立 → **无论门禁实际
#   成败都输出 "RESULT: ALL PASS" 并以 0 退出**。用不存在的构建树实测：日志里
#   `leak_probe => exit=1` 与 `RESULT: ALL PASS` 同时出现。这是 D72（给失败产物开绿灯）
#   的同一类假绿，且位置更致命——它是"门禁的门禁"。
#   修法：① 用 $script:results 显式写脚本作用域；② 汇总必须能自检（条数!=预期即 FAIL）；
#   ③ ExitCode 为 $null 时判 NOEXIT 而非 PASS；④ 每行结果同时打到 stdout，调用方不必
#   只靠摘要行判断。
$results = @()
$script:results = @()
$EXPECTED_GATES = 8

function Invoke-Gate($name, $argv) {
    L "--- $name ---"
    $p = Start-Process -FilePath $argv[0] -ArgumentList $argv[1..($argv.Count - 1)] `
        -PassThru -NoNewWindow -RedirectStandardOutput "$env:TEMP\gate_out.txt" `
        -RedirectStandardError "$env:TEMP\gate_err.txt" -Wait
    $txt = (Get-Content "$env:TEMP\gate_out.txt" -Raw -ErrorAction SilentlyContinue) +
           (Get-Content "$env:TEMP\gate_err.txt" -Raw -ErrorAction SilentlyContinue)
    ($txt -split "`n" | ForEach-Object { L ("   " + $_.TrimEnd()) })
    $code = $p.ExitCode
    if ($null -eq $code) {
        $res = 'NOEXIT'                       # 拿不到退出码：不可信，按失败处理
    } elseif ($code -eq 0) {
        $res = 'PASS'
    } else {
        $res = 'FAIL'
    }
    $row = [pscustomobject]@{ Gate = $name; Exit = $code; Result = $res }
    $script:results += $row
    L ("   => exit={0}  {1}" -f $code, $res)
    Write-Host ("[{0}] {1} (exit={2})" -f $res, $name, $code) -ForegroundColor `
        $(if ($res -eq 'PASS') { 'Green' } else { 'Red' })
}

Invoke-Gate 'verify_sources'        @($PY, '-X', 'utf8', 'win_scripts\verify_sources.py')
Invoke-Gate 'flag_stability(A-F)'   @($PY, '-X', 'utf8', '.bugreview\flag_stability.py')
Invoke-Gate 'loader_edge_test2'     @($PY, '-X', 'utf8', '.bugreview\loader_edge_test2.py')
Invoke-Gate 'loader_edge_test3'     @($PY, '-X', 'utf8', '.bugreview\loader_edge_test3.py')
Invoke-Gate 'A6 builtin flags'      @('powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                                      '-File', 'benchmark\tools\verify_builtin_flags.ps1',
                                      '-ChromeExe', "$OutDir\chrome.exe")
Invoke-Gate 'flag_runtime_state'    @($PY, '-X', 'utf8', '.bugreview\flag_runtime_state.py',
                                      '--chrome', "$OutDir\chrome.exe")
Invoke-Gate 'leak_probe(2x15)'      @($PY, '-X', 'utf8', 'benchmark\tools\leak_probe.py',
                                      '--chrome', "$OutDir\chrome.exe", '--rounds', '2',
                                      '--tabs', '15', '--label', 'finalgate')
Invoke-Gate 'package_m155(门禁)'    @($PY, '-X', 'utf8', '.bugreview\package_m155.py')

L '=== 汇总 ==='
Write-Host ''
Write-Host '=== 收口门禁汇总 ===' -ForegroundColor Cyan
$results | ForEach-Object {
    L ("{0,-24} exit={1,-6} {2}" -f $_.Gate, $_.Exit, $_.Result)
    Write-Host ("  {0,-24} exit={1,-6} {2}" -f $_.Gate, $_.Exit, $_.Result)
}
if ($results.Count -ne $EXPECTED_GATES) {
    L ("RESULT: FAIL（汇总不完整：采集 {0} 条，预期 {1} 条——门禁自身坏了，别当通过）" `
        -f $results.Count, $EXPECTED_GATES)
    Write-Host ("RESULT: FAIL 汇总不完整 {0}/{1}" -f $results.Count, $EXPECTED_GATES) -ForegroundColor Red
    exit 1
}
$bad = @($results | Where-Object { $_.Result -ne 'PASS' })
if ($bad.Count -eq 0) {
    L "RESULT: ALL PASS（$EXPECTED_GATES/$EXPECTED_GATES）"
    Write-Host "RESULT: ALL PASS ($EXPECTED_GATES/$EXPECTED_GATES)" -ForegroundColor Green
    exit 0
}
L ("RESULT: FAIL x{0}: {1}" -f $bad.Count, (($bad | ForEach-Object { $_.Gate }) -join ', '))
Write-Host ("RESULT: FAIL x{0}: {1}" -f $bad.Count, (($bad | ForEach-Object { $_.Gate }) -join ', ')) -ForegroundColor Red
exit 1
