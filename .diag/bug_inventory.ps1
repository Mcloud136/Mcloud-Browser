# bug_inventory.ps1 - step 1: language & surface inventory + toolchain check
$ErrorActionPreference = 'SilentlyContinue'
$repo = 'd:\wxmuma\thorium'
$tree = 'D:\wxmuma\chromium-src\src'

Write-Output "=== [1] repo custom-code surface by area (files) ==="
foreach ($d in @('src','pak_src','win_scripts','benchmark','other','infra','arm')) {
    $p = Join-Path $repo $d
    if (Test-Path $p) {
        $exts = Get-ChildItem $p -Recurse -File | Group-Object Extension | Sort-Object Count -Descending | Select-Object -First 4 | ForEach-Object { "$($_.Name)x$($_.Count)" }
        "{0,-12} {1} files  [{2}]" -f $d, (Get-ChildItem $p -Recurse -File).Count, ($exts -join ', ')
    }
}

Write-Output "=== [2] toolchain availability ==="
$clang = Join-Path $tree 'third_party\llvm-build\Release+Asserts\bin\clang.exe'
"clang(ASan-capable): $(Test-Path $clang)  $clang"
$clangrt = Get-ChildItem (Split-Path $clang) -Filter 'clang_rt*' -Directory | Select-Object -First 1
"clang_rt dir: $($clangrt.Name)"
"clang --version:"; & $clang --version | Select-Object -First 1
$py = 'D:\wxmuma\depot_tools\bootstrap-2@3_11_8_chromium_35_bin\python3\bin\python3.exe'
"bootstrap python: $(Test-Path $py)"; & $py --version
"system python:"; where.exe python 2>&1 | Select-Object -First 1
where.exe gcc 2>&1 | Select-Object -First 1

Write-Output "=== [3] test inputs ==="
"default.pak: $(Test-Path (Join-Path $tree 'out\mcloud\resources\default.pak'))"
Get-ChildItem (Join-Path $tree 'out\mcloud\resources') -Filter '*.pak' -ErrorAction SilentlyContinue | Select-Object Name, @{N='MB';E={[math]::Round($_.Length/1MB,1)}} | Format-Table -AutoSize | Out-String
"pak_src files:"; Get-ChildItem (Join-Path $repo 'pak_src') -File | Select-Object Name, Length | Format-Table -AutoSize | Out-String

Write-Output "=== [4] workspace state ==="
"git in PATH: $(where.exe git 2>&1 | Select-Object -First 1)"
"portable git: $(Test-Path 'D:\sd-webui-aki-v4.11.1-cu128\git\cmd\git.exe')"
".diag dir: "; Get-ChildItem (Join-Path $repo '.diag') -File | Select-Object -ExpandProperty Name

Write-Output "=== [5] installed browser experiment state ==="
Get-Item "$env:LOCALAPPDATA\Chromium\Application\mcloud_flags.txt", "$env:LOCALAPPDATA\Chromium\Application\mcloud_flags.txt.bak-20260922" | Select-Object Name, LastWriteTime | Format-Table -AutoSize | Out-String
$proc = Get-Process chrome -ErrorAction SilentlyContinue
"chrome running: $($null -ne $proc) count=$($proc.Count)"
