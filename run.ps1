# OpenAGY: Windows PowerShell Runner
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

$venvPython = Join-Path $ScriptDir "venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "[*] Ambiente virtual nao encontrado. Executando instalacao inicial..." -ForegroundColor Yellow
    & ".\install.ps1"
}

Write-Host " Iniciando OpenAGY Bridge..." -ForegroundColor Cyan
& $venvPython main.py @args
