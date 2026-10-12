@echo off
setlocal EnableExtensions EnableDelayedExpansion
if exist "%SystemRoot%\SysWOW64\cmd.exe" set x64=1
rem Prefer the binary rebuilt from pak_src_fixed/pak.c and byte-verified against
rem real Chromium .pak corpora; the prebuilt MinGW pair predates the source
rem (no .gz magic table) and stays only as a fallback. (ASCII: .bat is read in
rem the OEM codepage, so non-ASCII comments would show as mojibake.)
set core_x64=pak_msvc64.exe
if not exist "%core_x64%" if exist pak_mingw64.exe set core_x64=pak_mingw64.exe
set core_x86=pak_msvc32.exe
if not exist "%core_x86%" if exist pak_mingw32.exe set core_x86=pak_mingw32.exe
set "WORK_DIR=%~dp0"
set "file=%~1"
set unpack_dir=%~dpn1_unpacked
if not exist "%WORK_DIR%" md "%WORK_DIR%"
pushd "%WORK_DIR%"
if "%x64%"=="1" ( set core=%core_x64% ) else ( set core=%core_x86% )
if not exist %core% echo core program (%core%) NOT FOUND! &pause &exit
if not exist "%unpack_dir%" md "%unpack_dir%"
if exist "%file%" %core% -u "%file%" "%unpack_dir%"
if exist "%unpack_dir%\pak_index.ini" echo Unpacked "%file%" to "%unpack_dir%"
timeout /t 5||pause