# OpenAGY: Windows PowerShell Installer & Configurator
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  OpenAGY: Instalacao e Configuracao para o OpenCode (Windows)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 1. Detectar Python
$pythonCmd = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonCmd = "python"
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonCmd = "py"
} elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
    $pythonCmd = "python3"
}

if (-not $pythonCmd) {
    Write-Host "[X] Erro: Python 3 nao foi encontrado no PATH." -ForegroundColor Red
    Write-Host "    Baixe e instale o Python em https://www.python.org/ (marque 'Add Python to PATH')." -ForegroundColor Yellow
    exit 1
}

$pyVersion = & $pythonCmd --version
Write-Host "[v] Python detectado: $pyVersion" -ForegroundColor Green

# 2. Verificar Antigravity CLI (agy)
$agyCmd = Get-Command agy -ErrorAction SilentlyContinue
if ($agyCmd) {
    Write-Host "[v] Antigravity CLI encontrado: $($agyCmd.Source)" -ForegroundColor Green
} else {
    $localAgy = Join-Path $env:USERPROFILE ".local\bin\agy.exe"
    if (Test-Path $localAgy) {
        Write-Host "[v] Antigravity CLI encontrado em: $localAgy" -ForegroundColor Green
    } else {
        Write-Host "[!] Aviso: 'agy' nao foi encontrado no PATH. Certifique-se de que o Antigravity esta instalado." -ForegroundColor Yellow
    }
}

# 3. Criar venv se necessario
$venvPath = Join-Path $ScriptDir "venv"
if (-not (Test-Path $venvPath)) {
    Write-Host "[*] Criando ambiente virtual Python (venv)..." -ForegroundColor Cyan
    & $pythonCmd -m venv venv
}

# 4. Ativar venv e instalar dependencias
$venvPython = Join-Path $venvPath "Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "[X] Executavel Python do venv nao encontrado em $venvPython" -ForegroundColor Red
    exit 1
}

Write-Host "[*] Instalando dependencias..." -ForegroundColor Cyan
& $venvPython -m pip install -q --upgrade pip
& $venvPython -m pip install -q -r requirements.txt

# 5. Executar script de configuracao do OpenCode
Write-Host ""
& $venvPython setup_opencode.py @args

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Instalacao e Configuracao Concluidas com Sucesso!" -ForegroundColor Green
Write-Host ""
Write-Host " Como iniciar a ponte:" -ForegroundColor White
Write-Host "   .\run.ps1" -ForegroundColor Yellow
Write-Host "   (ou run.bat no Prompt de Comando)" -ForegroundColor Gray
Write-Host ""
Write-Host " Modelos prontos no OpenCode:" -ForegroundColor White
Write-Host "   - openagy/gemini-3.8-flash-medium (Padrao para chat e subagentes)" -ForegroundColor Cyan
Write-Host "   - openagy/gemini-3.8-flash-low (Ultra rapido)" -ForegroundColor Cyan
Write-Host "   - openagy/gemini-3.8-flash-high (Raciocinio profundo)" -ForegroundColor Cyan
Write-Host "   - openagy/gemini-3.1-pro-high" -ForegroundColor Cyan
Write-Host "   - openagy/claude-sonnet-5-5-high" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Green
