@echo off
call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
echo.
echo VC_DONE errorlevel=%errorlevel%
echo.
echo PATH contains MSVC bin?
echo %PATH% | findstr /i "MSVC" || echo   (no MSVC in PATH)
echo.
if exist "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Tools\MSVC\14.51.36231\bin\Hostx64\x64\cl.exe" (
  echo cl.exe EXISTS at known path
) else (
  echo cl.exe MISSING at known path
)
where cl 2>nul || echo cl not on PATH
