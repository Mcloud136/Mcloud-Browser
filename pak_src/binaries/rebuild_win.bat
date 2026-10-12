@echo off
rem Thin wrapper: the real work lives in ..\..\.bugreview\pak_rebuild.py
rem (env-var handling, the two arch builds, and the byte-for-byte validation
rem against real Chromium .pak corpora). Kept as a .bat so the upstream-style
rem entry point still works. NOTE: this file must stay CRLF + ASCII -- cmd
rem reads .bat in the OEM codepage, and do NOT reuse the name TMP for a
rem local variable: overriding %TMP% breaks cmd's own temp-file handling
rem (measured here: the build silently produced nothing).
setlocal
cd /d %~dp0
python ..\..\.bugreview\pak_rebuild.py
endlocal
exit /b %ERRORLEVEL%
