@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

if not exist "venv\Scripts\activate.bat" (
    echo [*] Ambiente virtual nao encontrado. Executando instalacao primeiro...
    call install.bat
    if %errorlevel% neq 0 exit /b 1
)

call venv\Scripts\activate.bat

echo [*] Iniciando OpenAGY Bridge no Windows...
python main.py %*
