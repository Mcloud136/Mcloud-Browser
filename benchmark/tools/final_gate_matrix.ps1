# final_gate_matrix.ps1 - 收口门禁矩阵：一条命令跑完全部验证并给出每项 PASS/FAIL
# 由第3周期 bug-review 固化而来（原 .bugreview/cycle3_final_gate.ps1）。默认针对 M155 构建树，
# 可用环境变量 LOADER_TEST_OUT / 参数 -OutDir 换目标树；任何一项 FAIL 都以非零码退出。
# 用法：构建链跑完后执行；任何一项 FAIL 都以非零码退出。
$ErrorActionPreference = 'Continue'
$LOG = 'D:\wxmuma\thorium\.bugreview\cycle3_final_gate.log'
Set-Content -LiteralPath $LOG -Value ("[{0}] === 收口门禁开始 ===" -f (Get-Date -Format 's')) -Encoding UTF8
function L($m) { Add-Content -LiteralPath $LOG -Value ("[{0}] {1}" -f (Get-Date -Format 's'), $m) -Encoding UTF8 }
$PY = 'C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe'
param([string]$OutDir = '')
if (-not $OutDir) { $OutDir = 'D:\wxmuma\chromium-src-155\src\out\mcloud' }
$env:LOADER_TEST_OUT = $OutDir
$env:PYTHONUTF8 = '1'
Set-Location 'D:\wxmuma\thorium'

$results = @()
function Invoke-Gate($name, $argv) {
    L "--- $name ---"
    $p = Start-Process -FilePath $argv[0] -ArgumentList $argv[1..($argv.Count - 1)] `
        -PassThru -NoNewWindow -RedirectStandardOutput "$env:TEMP\gate_out.txt" `
        -RedirectStandardError "$env:TEMP\gate_err.txt" -Wait
    $txt = (Get-Content "$env:TEMP\gate_out.txt" -Raw -ErrorAction SilentlyContinue) +
           (Get-Content "$env:TEMP\gate_err.txt" -Raw -ErrorAction SilentlyContinue)
    ($txt -split "`n" | ForEach-Object { L ("   " + $_.TrimEnd()) })
    $ok = ($p.ExitCode -eq 0)
    $results += [pscustomobject]@{ Gate = $name; Exit = $p.ExitCode; Result = $(if ($ok) { 'PASS' } else { 'FAIL' }) }
    L ("   => exit=" + $p.ExitCode)
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
$results | ForEach-Object { L ("{0,-24} exit={1,-4} {2}" -f $_.Gate, $_.Exit, $_.Result) }
$bad = @($results | Where-Object { $_.Result -ne 'PASS' })
if ($bad.Count -eq 0) {
    L 'RESULT: ALL PASS'
    exit 0
}
L ("RESULT: FAIL x{0}: {1}" -f $bad.Count, (($bad | ForEach-Object { $_.Gate }) -join ', '))
exit 1
