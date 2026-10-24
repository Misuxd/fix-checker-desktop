$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath ".\.venv\Scripts\python.exe")) {
    throw "Double-click setup.bat first (Python 3.12 or later is required)."
}
& ".\.venv\Scripts\python.exe" main.py
