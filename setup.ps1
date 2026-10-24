param([string]$Python = "")
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Installation failed (exit code $LASTEXITCODE): $Executable $Arguments"
    }
}

function Get-PythonExecutable {
    param([string]$Command, [string[]]$PrefixArguments = @())
    # Resolve the base interpreter even when launched from an existing venv.
    $probe = "import os, sys; assert sys.version_info >= (3, 12); import tkinter, venv, ensurepip; print(os.path.join(sys.base_prefix, 'python.exe'))"
    try {
        $result = & $Command @PrefixArguments -c $probe 2>$null
        if ($LASTEXITCODE -eq 0 -and $result) {
            $executable = ([string]($result | Select-Object -Last 1)).Trim()
            if (Test-Path -LiteralPath $executable -PathType Leaf) {
                return $executable
            }
        }
    } catch {
        # Try the next installed interpreter.
    }
    return $null
}

if ($Python) {
    $pythonExecutable = Get-PythonExecutable $Python
    if (-not $pythonExecutable) {
        throw "Cannot use '$Python'. Choose Python 3.12 or newer with Tcl/Tk, venv and pip installed."
    }
} else {
    $candidates = @(
        @{ Command = "py"; Prefix = @("-3.12") },
        @{ Command = ".\.venv\Scripts\python.exe"; Prefix = @() },
        @{ Command = ".\.skyvern-venv\Scripts\python.exe"; Prefix = @() },
        @{ Command = "py"; Prefix = @("-3") },
        @{ Command = "python"; Prefix = @() },
        @{ Command = "python3"; Prefix = @() }
    )
    $pythonExecutable = $null
    foreach ($candidate in $candidates) {
        $pythonExecutable = Get-PythonExecutable $candidate.Command $candidate.Prefix
        if ($pythonExecutable) { break }
    }
    if (-not $pythonExecutable) {
        throw "Python 3.12 or newer was not found. Install Python from https://www.python.org/downloads/windows/ with the Python launcher, Tcl/Tk and pip, then double-click setup.bat again."
    }
}

Write-Host "Using Python: $pythonExecutable"
$environments = @(
    @{ Directory = ".venv"; Requirements = "requirements.txt"; Name = "Application" },
    @{ Directory = ".skyvern-venv"; Requirements = "requirements-skyvern.txt"; Name = "Skyvern" }
)
foreach ($environment in $environments) {
    Write-Host "`nInstalling $($environment.Name) dependencies..."
    Invoke-Checked $pythonExecutable @("-m", "venv", $environment.Directory)
    $environmentPython = Join-Path $PSScriptRoot "$($environment.Directory)\Scripts\python.exe"
    Invoke-Checked $environmentPython @("-m", "ensurepip", "--upgrade")
    Invoke-Checked $environmentPython @("-m", "pip", "install", "--upgrade", "pip")
    Invoke-Checked $environmentPython @("-m", "pip", "install", "-r", $environment.Requirements)
    Invoke-Checked $environmentPython @("-m", "pip", "check")
    Invoke-Checked $environmentPython @("-m", "playwright", "install", "chromium")
}

Write-Host "`nReady. Double-click start.bat to launch FIX Checker."
