@echo off
setlocal
title FIX Checker - Setup
pushd "%~dp0"
if errorlevel 1 exit /b 1

echo Installing FIX Checker dependencies. This can take several minutes.
echo Keep this window open until setup finishes.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*
set "setup_exit=%errorlevel%"
echo.
if "%setup_exit%"=="0" (
    echo Setup completed. Double-click start.bat to launch FIX Checker.
) else (
    echo Setup failed. Read the error above, then run setup.bat again.
)
pause
popd
exit /b %setup_exit%
