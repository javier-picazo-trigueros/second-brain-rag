#requires -Version 5.1
<#
.SYNOPSIS
  Tareas del proyecto. Uso: .\tasks.ps1 <install|test|lint|typecheck|audit|up|index|watch|serve|dev|web-install|web-test|web-lint|web-typecheck|web-build|web-dev>
.NOTES
  El venv vive fuera del repo (OneDrive). Se puede cambiar con $env:BRAIN_VENV.
#>
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("install", "test", "lint", "typecheck", "audit", "up", "index", "watch", "serve", "dev",
        "web-install", "web-test", "web-lint", "web-typecheck", "web-build", "web-dev")]
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

# La interfaz usa pnpm 10 (junctions): node_modules queda casi entero fuera de OneDrive.
# No uses `npm install` en frontend/: reemplazaría los enlaces por una carpeta real.
$WebHome = "C:\venvs\second-brain-web"
$Pnpm = Join-Path $WebHome "tools10\node_modules\.bin\pnpm.cmd"

function Install-Pnpm {
    if (Test-Path $Pnpm) { return }
    $tools = Join-Path $WebHome "tools10"
    New-Item -ItemType Directory -Force $tools | Out-Null
    if (-not (Test-Path (Join-Path $tools "package.json"))) {
        Set-Content (Join-Path $tools "package.json") '{"name":"tools10","private":true}'
    }
    Invoke-Checked "npm" @("install", "pnpm@10.34.9", "--prefix", $tools, "--no-audit", "--no-fund")
}

function Invoke-Web {
    param([string[]]$PnpmArgs)
    Install-Pnpm
    Push-Location (Join-Path $PSScriptRoot "frontend")
    try { Invoke-Checked $Pnpm $PnpmArgs } finally { Pop-Location }
}

switch ($Task) {
    "install" {
        if (-not (Test-Path $Py)) { Invoke-Checked "python" @("-m", "venv", $Venv) }
        # El pip incluido en un venv nuevo (24.0) no valida los certificados actuales de PyPI:
        # se actualiza usando el pip del Python que creó el venv.
        Invoke-Checked "python" @("-m", "pip", "--python", $Py, "install", "--upgrade", "pip")
        Invoke-Checked $Py @("-m", "pip", "install", "-e", ".[dev]")
        # Hook pre-push versionado: ejecuta la auditoría de privacidad antes de cada push.
        Invoke-Checked "git" @("config", "--local", "core.hooksPath", ".githooks")
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
    "audit" {
        # Rutas y títulos del vault, datos personales, autoría y menciones a una IA. Falla (código 1)
        # si encuentra algo; sin manifest omite solo las comprobaciones del vault.
        Assert-Venv
        Invoke-Checked $Py (@("-m", "secondbrain.privacy_audit") + $Rest)
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
    "web-install" { Invoke-Web @("install") }
    "web-test" { Invoke-Web (@("test") + $Rest) }
    "web-lint" { Invoke-Web @("lint") }
    "web-typecheck" { Invoke-Web @("typecheck") }
    "web-build" { Invoke-Web @("build") }
    "web-dev" { Invoke-Web @("dev") }
    "dev" {
        Assert-Venv
        Write-Host "dev (API + interfaz) se implementa en la Fase 3."
    }
}
