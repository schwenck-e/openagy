@echo off
setlocal enabledelayedexpansion

echo ============================================================
echo   OpenAGY: Instalacao e Configuracao para o OpenCode (Windows)
echo ============================================================

cd /d "%~dp0"

:: 1. Detectar Python
set PYTHON_CMD=
where python >nul 2>nul
if %errorlevel% equ 0 (
    set PYTHON_CMD=python
) else (
    where py >nul 2>nul
    if %errorlevel% equ 0 (
        set PYTHON_CMD=py
    ) else (
        where python3 >nul 2>nul
        if %errorlevel% equ 0 (
            set PYTHON_CMD=python3
        )
    )
)

if "%PYTHON_CMD%"=="" (
    echo [X] Erro: Python 3 nao foi encontrado no PATH do sistema.
    echo     Baixe e instale o Python em: https://www.python.org/
    echo     Certifique-se de marcar a opcao "Add Python to PATH" durante a instalacao.
    exit /b 1
)

echo [v] Python detectado: %PYTHON_CMD%
%PYTHON_CMD% --version

:: 2. Verificar Antigravity CLI local (agy)
where agy >nul 2>nul
if %errorlevel% equ 0 (
    echo [v] Antigravity CLI local encontrado no PATH.
) else (
    if exist "%USERPROFILE%\.local\bin\agy.exe" (
        echo [v] Antigravity CLI encontrado em: %USERPROFILE%\.local\bin\agy.exe
    ) else (
        if exist "%LOCALAPPDATA%\Programs\antigravity\bin\agy.exe" (
            echo [v] Antigravity CLI encontrado em: %LOCALAPPDATA%\Programs\antigravity\bin\agy.exe
        ) else (
            echo [!] Aviso: 'agy' nao foi encontrado no PATH padrao. Certifique-se de que o Antigravity esta instalado.
        )
    )
)

:: 3. Criar ambiente virtual se nao existir
if not exist "venv" (
    echo [*] Criando ambiente virtual Python (venv)...
    %PYTHON_CMD% -m venv venv
    if %errorlevel% neq 0 (
        echo [X] Falha ao criar ambiente virtual com %PYTHON_CMD% -m venv.
        exit /b 1
    )
)

:: 4. Ativar ambiente virtual e instalar dependencias
echo [*] Instalando dependencias no ambiente virtual...
call venv\Scripts\activate.bat
python -m pip install -q --upgrade pip
python -m pip install -q -r requirements.txt

:: 5. Executar configuracao do OpenCode
echo.
python setup_opencode.py %*

echo.
echo ============================================================
echo  Instalacao e Configuracao Concluidas com Sucesso!
echo.
echo  Como iniciar a ponte:
echo  1. Execute: run.bat
echo     (ou no PowerShell: .\run.ps1)
echo.
echo  2. Abra o OpenCode e use qualquer modelo OpenAGY no seletor:
echo     - openagy/gemini-3.8-flash-medium (Padrao para chat e subagentes)
echo     - openagy/gemini-3.8-flash-low (Ultra rapido)
echo     - openagy/gemini-3.8-flash-high (Raciocinio profundo)
echo     - openagy/gemini-3.1-pro-high
echo     - openagy/claude-sonnet-5-5-high
echo ============================================================
