$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath ".\.venv\Scripts\python.exe")) {
    throw "Run .\setup.ps1 first (Python 3.12 or later is required)."
}
& ".\.venv\Scripts\python.exe" main.py
