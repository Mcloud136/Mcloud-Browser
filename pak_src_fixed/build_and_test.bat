@echo off
REM Configure MSVC env manually (avoid vcvarsall.bat, which calls the sandbox-blocked reg.exe).
set "VC=C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Tools\MSVC\14.51.36231"
set "SDK=C:\Program Files (x86)\Windows Kits\10"
set "SDKVER=10.0.26100.0"
set "INCLUDE=%VC%\include;%SDK%\Include\%SDKVER%\ucrt;%SDK%\Include\%SDKVER%\um;%SDK%\Include\%SDKVER%\shared"
set "LIB=%VC%\lib\x64;%SDK%\Lib\%SDKVER%\ucrt\x64;%SDK%\Lib\%SDKVER%\um\x64"
set "PATH=%PATH%;%VC%\bin\Hostx64\x64"

echo == Compile (cl /W4 /utf-8; 不再用 /wd4819 压掉编码警告) ==
REM 源文件含中文注释且无 BOM：不加 /utf-8 时 cl 按系统代码页(936)解码，会把 UTF-8 的
REM 换行吞进双字节字符里 —— 实测 19 行被合并（同一处 sscanf 的告警行号 384 vs 真实 403）。
REM 后果是"中文注释行吃掉下一行代码"的静默失效，属于必须显式处理而不是压掉警告的问题（D192）。
"%VC%\bin\Hostx64\x64\cl.exe" /W4 /O2 /utf-8 /D_CRT_SECURE_NO_WARNINGS /nologo pak.c /Fe:pak.exe
if errorlevel 1 (echo BUILD FAILED & exit /b 1)

echo == Prepare samples ==
if exist t_in rmdir /s /q t_in
if exist t_out rmdir /s /q t_out
if exist pak_test.pak del pak_test.pak
mkdir t_in
echo ^<!doctype html^>^<html^>hi^</html^> > t_in\1.html
powershell -NoProfile -Command "$b = [byte[]]@(0x89,0x50,0x4E,0x47,0x0D,0x0A,0x1A,0x0A) + [System.Text.Encoding]::ASCII.GetBytes('PNGDATA'); [io.file]::WriteAllBytes('t_in\2.png', $b)"

(
echo [Global]
echo version=5
echo encoding=0
echo.
echo [Resources]
echo 1=1.html
echo 2=2.png
echo.
echo [Alias]
echo 10=1
) > t_in\pak_index.ini

echo == Pack ==
pak.exe -p t_in\pak_index.ini pak_test.pak
if errorlevel 1 (echo PACK FAILED & exit /b 1)

echo == Unpack ==
pak.exe -u pak_test.pak t_out
if errorlevel 1 (echo UNPACK FAILED & exit /b 1)

echo == Verify round-trip ==
fc t_in\1.html t_out\1.html >nul && echo [OK] 1.html identical
fc t_in\2.png t_out\2.png >nul && echo [OK] 2.png identical
echo == t_out listing ==
dir t_out
