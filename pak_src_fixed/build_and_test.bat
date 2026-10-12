@echo off
REM Configure MSVC env manually (avoid vcvarsall.bat, which calls the sandbox-blocked reg.exe).
set "VC=C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Tools\MSVC\14.51.36231"
set "SDK=C:\Program Files (x86)\Windows Kits\10"
set "SDKVER=10.0.26100.0"
set "INCLUDE=%VC%\include;%SDK%\Include\%SDKVER%\ucrt;%SDK%\Include\%SDKVER%\um;%SDK%\Include\%SDKVER%\shared"
set "LIB=%VC%\lib\x64;%SDK%\Lib\%SDKVER%\ucrt\x64;%SDK%\Lib\%SDKVER%\um\x64"
set "PATH=%PATH%;%VC%\bin\Hostx64\x64"

echo == Compile (cl /W4, Chinese comments suppressed via /wd4819) ==
"%VC%\bin\Hostx64\x64\cl.exe" /W4 /O2 /wd4819 /D_CRT_SECURE_NO_WARNINGS /nologo pak.c /Fe:pak.exe
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
