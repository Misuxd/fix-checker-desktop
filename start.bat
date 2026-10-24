@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Double-click setup.bat first to install the dependencies.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" main.py
if errorlevel 1 pause
