@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0" || exit /b 1

set "PYTHON312="
set "PYTHON_MANAGER="
set "PYTHON_CHECK=import sys; valid = sys.version_info[:2] == (3, 12) and sys.maxsize > 2**32; print(sys.executable if valid else ''); sys.exit(0 if valid else 1)"

call :find_python
if defined PYTHON312 goto setup

echo 64-bit Python 3.12 was not found. Installing it alongside any existing Python.
call :find_manager
if defined PYTHON_MANAGER goto install_python

where winget.exe >nul 2>&1
if errorlevel 1 (
    echo Python Install Manager and WinGet are unavailable.
    echo Install Python Install Manager from https://www.python.org/downloads/
    echo Then open a new terminal and run setup.bat again.
    goto failed
)

echo Installing Python Install Manager...
winget.exe install --id 9NQ7512CXL7T --exact --source msstore --accept-package-agreements --accept-source-agreements --disable-interactivity
if errorlevel 1 goto failed
call :find_manager
if not defined PYTHON_MANAGER (
    echo Python Install Manager is not accessible yet.
    echo Enable its app execution aliases, open a new terminal, and rerun setup.bat.
    goto failed
)

:install_python
echo Installing Python 3.12 using Python Install Manager...
"%PYTHON_MANAGER%" install 3.12
if errorlevel 1 goto failed
call :find_python
if not defined PYTHON312 (
    echo Installation finished, but a working 64-bit Python 3.12 was not found.
    goto failed
)

:setup
echo Using Python: "%PYTHON312%"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" -Python "%PYTHON312%"
if errorlevel 1 goto failed
pause
exit /b 0

:find_python
call :probe_python py -3.12
if defined PYTHON312 exit /b 0
if defined PYTHON_MANAGER (
    call :probe_python "%PYTHON_MANAGER%" exec -3.12
)
if defined PYTHON312 exit /b 0
call :probe_python python
exit /b 0

:probe_python
rem Capture only a successful probe; avoid nested cmd quoting for paths with spaces.
set "PYTHON_PROBE=%TEMP%\fix-checker-python-%RANDOM%-%RANDOM%.txt"
%* -c "%PYTHON_CHECK%" >"%PYTHON_PROBE%" 2>nul
if not errorlevel 1 set /p "PYTHON312=" <"%PYTHON_PROBE%"
del /q "%PYTHON_PROBE%" >nul 2>&1
exit /b 0

:find_manager
rem The legacy py launcher has no install command. pymanager avoids that conflict.
for %%M in (py.exe pymanager.exe "%LocalAppData%\Microsoft\WindowsApps\pymanager.exe" "%LocalAppData%\Microsoft\WindowsApps\PythonSoftwareFoundation.PythonManager_3847v3x7pw1km\pymanager.exe" "%LocalAppData%\Microsoft\WindowsApps\PythonSoftwareFoundation.PythonManager_qbz5n2kfra8p0\pymanager.exe") do call :check_manager "%%~M"
exit /b 0

:check_manager
if defined PYTHON_MANAGER exit /b 0
"%~1" help install >nul 2>&1
if not errorlevel 1 set "PYTHON_MANAGER=%~1"
exit /b 0

:failed
echo.
echo Setup failed. Read the error above, then run setup.bat again.
pause
exit /b 1
