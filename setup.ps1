param([string]$Python = "python")
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Installation failed: $Executable $Arguments" }
}
Invoke-Checked $Python @("-m", "venv", ".venv")
Invoke-Checked ".\.venv\Scripts\python.exe" @("-m", "pip", "install", "-r", "requirements.txt")
Invoke-Checked $Python @("-m", "venv", ".skyvern-venv")
Invoke-Checked ".\.skyvern-venv\Scripts\python.exe" @("-m", "pip", "install", "-r", "requirements-skyvern.txt")
Invoke-Checked ".\.venv\Scripts\python.exe" @("-m", "playwright", "install", "chromium")
Write-Host "Ready. Run .\start.ps1"
