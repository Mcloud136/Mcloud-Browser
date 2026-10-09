# verify_flags_edit.ps1
$p = 'C:\Users\Administrator\AppData\Local\Chromium\Application\mcloud_flags.txt'
Write-Output "=== suspect lines (should all start with #) ==="
Select-String -Path $p -Pattern 'ThrottleUnimportantFrameRate|ReduceHardwareVideoDecoderBuffers|SkiaGraphite' | ForEach-Object { "{0}: {1}" -f $_.LineNumber, $_.Line }
Write-Output "=== active flag lines (start with --) ==="
(Select-String -Path $p -Pattern '^--').Count
Write-Output "=== any active suspect left? ==="
$bad = Select-String -Path $p -Pattern '^--enable-features=(ThrottleUnimportantFrameRate|ReduceHardwareVideoDecoderBuffers|SkiaGraphite|SkiaGraphitePrecompilation)'
if ($bad) { $bad | ForEach-Object { $_.Line } } else { "none - clean" }
