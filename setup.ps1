param([string]$Python = "python")
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Installation failed: $Executable $Arguments" }
}
function Initialize-Venv {
    param([string]$Directory)
    if (Test-Path -LiteralPath $Directory) {
        $Interpreter = Join-Path $Directory "Scripts\python.exe"
        $Compatible = $false
        if (Test-Path -LiteralPath $Interpreter) {
            & $Interpreter -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) and sys.maxsize > 2**32 else 1)"
            $Compatible = $LASTEXITCODE -eq 0
        }
        if (-not $Compatible) {
            $Backup = "$Directory-backup-$([guid]::NewGuid().ToString('N'))"
            Write-Host "Preserving incompatible or incomplete environment as $Backup"
            Move-Item -LiteralPath $Directory -Destination $Backup
        }
    }
    Invoke-Checked $Python @("-m", "venv", $Directory)
}

Invoke-Checked $Python @("-c", "import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) and sys.maxsize > 2**32 else '64-bit Python 3.12 is required. Run setup.bat to install it.')")
Initialize-Venv ".venv"
Invoke-Checked ".\.venv\Scripts\python.exe" @("-m", "pip", "install", "--upgrade", "pip")
Invoke-Checked ".\.venv\Scripts\python.exe" @("-m", "pip", "install", "-r", "requirements.txt")
Initialize-Venv ".skyvern-venv"
Invoke-Checked ".\.skyvern-venv\Scripts\python.exe" @("-m", "pip", "install", "--upgrade", "pip")
Invoke-Checked ".\.skyvern-venv\Scripts\python.exe" @("-m", "pip", "install", "-r", "requirements-skyvern.txt")
Invoke-Checked ".\.venv\Scripts\python.exe" @("-m", "playwright", "install", "chromium")
Write-Host "Ready. Run .\start.ps1"
