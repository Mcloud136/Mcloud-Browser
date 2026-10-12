# mcloud_flags_lookup.ps1 —— 按**加载器自己的口径**判断被测二进制能不能读到内置优化清单。
#
# 为什么要有这个文件（第7周期，缺陷 D183）：bench_memory / bench_startup /
# bench_navigation 三个量具此前都只问 "$exe 同目录有没有 mcloud_flags.txt"。
# 而安装版的布局是 `Application\chrome.exe` + `Application\<版本>\mcloud_flags.txt`
# （D105/D109：清单随版本目录投递，加载器 v8 以 DIR_MODULE = chrome.dll 所在目录为第一候选），
# 所以对**任何安装版**这三个脚本都会打印"缺失（内置优化不生效，结果无意义）"——
# 一句假阴性写在 KPI 日志里，而脚本照样 exit 0 输出数字。要么修判据，要么别再声称。
#
# 三个脚本共用本文件，避免同一套路径规则出现三份各自漂移的实现。

function Get-McloudFlagsProbe {
    <#
      输入：chrome.exe 的 FileInfo 对象。
      输出：[pscustomobject] @{ Found=.. ; Where=.. ; Path=.. }
      Where 用人话说明命中在哪一层，日志里要能看出"测的是带优化的还是裸的内核"。
    #>
    param([Parameter(Mandatory = $true)]$SubjectExe)

    $exeDir = $SubjectExe.DirectoryName
    # 1) DIR_MODULE 口径：chrome.dll 与 exe 同目录（dev/flat/portable 布局）
    if (Test-Path (Join-Path $exeDir 'chrome.dll')) {
        $flat = Join-Path $exeDir 'mcloud_flags.txt'
        if (Test-Path $flat) {
            return [pscustomobject]@{ Found = $true; Where = 'DIR_MODULE（与 chrome.dll 同目录）'; Path = $flat }
        }
        return [pscustomobject]@{ Found = $false; Where = 'DIR_MODULE 里没有'; Path = $flat }
    }
    # 2) 安装版布局：版本目录整批投递 chrome.dll，清单也在里面
    $candidates = @(Get-ChildItem -LiteralPath $exeDir -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^\d+(\.\d+){2,3}$' } |
        Where-Object { Test-Path (Join-Path $_.FullName 'chrome.dll') } |
        Sort-Object { [version]$_.Name } -Descending)
    foreach ($d in $candidates) {
        $p = Join-Path $d.FullName 'mcloud_flags.txt'
        if (Test-Path $p) {
            return [pscustomobject]@{ Found = $true; Where = ('版本目录 ' + $d.Name); Path = $p }
        }
    }
    # 3) 加载器的次候选：exe 同目录（根级残留），存在也只算"读到"，不算发布物投递
    $root = Join-Path $exeDir 'mcloud_flags.txt'
    if (Test-Path $root) {
        return [pscustomobject]@{ Found = $true; Where = 'exe 同目录（根级残留，非发布物投递，见 D109）'; Path = $root }
    }
    return [pscustomobject]@{ Found = $false; Where = '三处候选全都没有'; Path = $root }
}
