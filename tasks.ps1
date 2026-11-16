#requires -Version 5.1
<#
.SYNOPSIS
  Tareas del proyecto. Uso: .\tasks.ps1 <install|test|lint|typecheck|up|index|watch|serve|dev>
.NOTES
  El venv vive fuera del repo (OneDrive). Se puede cambiar con $env:BRAIN_VENV.
#>
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("install", "test", "lint", "typecheck", "up", "index", "watch", "serve", "dev")]
    [string]$Task,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = "Stop"
$Venv = if ($env:BRAIN_VENV) { $env:BRAIN_VENV } else { "C:\venvs\second-brain" }
$Py = Join-Path $Venv "Scripts\python.exe"
Set-Location $PSScriptRoot

function Invoke-Checked {
    param([string]$Exe, [string[]]$CmdArgs)
    # PS 5.1 trata el stderr de un exe nativo como error; aquí solo importa el código de salida.
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $Exe @CmdArgs
    $code = $LASTEXITCODE
    $ErrorActionPreference = $prev
    if ($code -ne 0) { throw "Falló: $Exe $($CmdArgs -join ' ') (código $code)" }
}

function Assert-Venv {
    if (-not (Test-Path $Py)) {
        throw "No existe el venv en $Venv. Créalo con: python -m venv $Venv"
    }
}

switch ($Task) {
    "install" {
        if (-not (Test-Path $Py)) { Invoke-Checked "python" @("-m", "venv", $Venv) }
        # El pip incluido en un venv nuevo (24.0) no valida los certificados actuales de PyPI:
        # se actualiza usando el pip del Python que creó el venv.
        Invoke-Checked "python" @("-m", "pip", "--python", $Py, "install", "--upgrade", "pip")
        Invoke-Checked $Py @("-m", "pip", "install", "-e", ".[dev]")
    }
    "test" {
        Assert-Venv
        Invoke-Checked $Py (@("-m", "pytest") + $Rest)
    }
    "lint" {
        Assert-Venv
        Invoke-Checked $Py @("-m", "ruff", "check", "src", "tests")
        Invoke-Checked $Py @("-m", "ruff", "format", "--check", "src", "tests")
    }
    "typecheck" {
        Assert-Venv
        Invoke-Checked $Py @("-m", "mypy")
    }
    "up" {
        Invoke-Checked "docker" @("compose", "up", "-d", "qdrant")
    }
    "index" {
        Assert-Venv
        Invoke-Checked $Py (@("-m", "secondbrain.cli", "index") + $Rest)
    }
    "watch" {
        Assert-Venv
        Invoke-Checked $Py (@("-m", "secondbrain.cli", "watch") + $Rest)
    }
    "serve" {
        Assert-Venv
        Invoke-Checked $Py (@("-m", "secondbrain.cli", "serve") + $Rest)
    }
    "dev" {
        Assert-Venv
        Write-Host "dev (API + interfaz) se implementa en la Fase 3."
    }
}
