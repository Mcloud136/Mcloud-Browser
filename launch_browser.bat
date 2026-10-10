@echo off
REM MCloud Browser launcher (Windows).
REM Sets the development Google API keys required at runtime (ADR-001: public dev keys, kept in repo).
REM
REM Bug-review D101 (2026-10-11): this script used to hard-code the M151 rollback tree
REM (D:\wxmuma\chromium-src\src\out\mcloud), so double-clicking it launched the OLD kernel
REM while looking like the new build. It also forced --enable-logging=1 --v=1 on every start,
REM which writes chrome_debug.log and skews cold-start (K1) timing. Both fixed below.
REM
REM Knobs (all optional):
REM   MCHROME_OUT     build output dir to launch        (default: current M155 tree)
REM   MCLOUD_PROFILE  persistent profile for manual test (default: %LOCALAPPDATA%\MCloudManual)
REM   MCLOUD_LOGGING  set to 1 to enable verbose chrome logging
REM Anything else you pass is forwarded to chrome.exe as-is.

if defined MCHROME_OUT (set "BUILDDIR=%MCHROME_OUT%") else (set "BUILDDIR=D:\wxmuma\chromium-src-155\src\out\mcloud")

set GOOGLE_API_KEY=AIzaSyCgcLY25b1jTb6Z1_8VA2hjX9HGPuYwmJY
set GOOGLE_DEFAULT_CLIENT_ID=77185425430.apps.googleusercontent.com
set GOOGLE_DEFAULT_CLIENT_SECRET=OTJgU3nD3q0q0q0q0q0q0q0q

if not exist "%BUILDDIR%\chrome.exe" (
  echo [ERROR] chrome.exe not found in "%BUILDDIR%"
  echo         set MCHROME_OUT to the build output directory you want to launch.
  exit /b 2
)

set "LOGARGS="
if "%MCLOUD_LOGGING%"=="1" set "LOGARGS=--enable-logging=1 --v=1"

if not defined MCLOUD_PROFILE set "MCLOUD_PROFILE=%LOCALAPPDATA%\MCloudManual"

echo Launching: "%BUILDDIR%\chrome.exe"
echo Profile  : "%MCLOUD_PROFILE%"
echo Flags    : built-in mcloud_flags.txt loaded by the browser (same directory)

cd /d "%BUILDDIR%"
start "" chrome.exe --user-data-dir="%MCLOUD_PROFILE%" %LOGARGS% %*
