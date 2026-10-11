#!/usr/bin/env bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "============================================================"
echo " 🚀 OpenAGY: Instalação e Configuração para o OpenCode"
echo "============================================================"

# 1. Verificar Python 3
PYTHON_BIN=""
if command -v python3 &> /dev/null; then
    PYTHON_BIN="python3"
elif command -v python &> /dev/null; then
    # Verificar se python é versão 3
    if python -c "import sys; sys.exit(0 if sys.version_info[0] >= 3 else 1)" 2>/dev/null; then
        PYTHON_BIN="python"
    fi
fi

if [ -z "$PYTHON_BIN" ]; then
    echo "❌ Python 3 é obrigatório, mas não foi encontrado no seu PATH."
    echo "   No Linux (Debian/Ubuntu): sudo apt install python3 python3-venv python3-pip"
    echo "   No Linux (Fedora/RHEL):   sudo dnf install python3 python3-pip"
    echo "   No Linux (Arch):          sudo pacman -S python python-pip"
    exit 1
fi
echo "✓ Python 3 encontrado: $($PYTHON_BIN --version) ($PYTHON_BIN)"

# 2. Verificar Antigravity CLI local (agy)
AGY_LOC=$(command -v agy 2>/dev/null || true)
if [ -z "$AGY_LOC" ]; then
    for candidate in "$HOME/.local/bin/agy" "$HOME/.gemini/antigravity-cli/bin/agy" "/usr/local/bin/agy" "/usr/bin/agy" "/opt/homebrew/bin/agy"; do
        if [ -x "$candidate" ]; then
            AGY_LOC="$candidate"
            break
        fi
    done
fi

if [ -n "$AGY_LOC" ]; then
    echo "✓ Antigravity CLI local encontrado em: $AGY_LOC"
else
    echo "⚠️  Aviso: 'agy' não foi encontrado no PATH padrão. Certifique-se de que o Antigravity está instalado."
fi

# 3. Criar e ativar ambiente virtual
if [ ! -d "venv" ]; then
    echo "📦 Criando ambiente virtual Python (venv)..."
    if ! "$PYTHON_BIN" -m venv venv 2>/dev/null; then
        echo "❌ Falha ao criar o ambiente virtual com '$PYTHON_BIN -m venv'."
        echo "   Em sistemas Debian/Ubuntu, instale o pacote correspondente:"
        echo "   sudo apt update && sudo apt install python3-venv python3-pip"
        exit 1
    fi
fi

echo "🔄 Ativando ambiente virtual e instalando dependências..."
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    python -m pip install -q --upgrade pip
    python -m pip install -q -r requirements.txt
else
    "$PYTHON_BIN" -m pip install -q -r requirements.txt
fi

# 4. Tornar scripts executáveis
chmod +x run.sh 2>/dev/null || true
chmod +x install.sh 2>/dev/null || true
chmod +x setup_opencode.py 2>/dev/null || true

# 5. Configurar o OpenCode
echo ""
if [ -f "venv/bin/python" ]; then
    venv/bin/python setup_opencode.py "$@"
else
    "$PYTHON_BIN" setup_opencode.py "$@"
fi

echo ""
echo "============================================================"
echo " ✅ Instalação e Configuração Concluídas!"
echo ""
echo " Como usar:"
echo " 1. Inicie a ponte local executando:"
echo "    ./run.sh"
echo ""
echo " 2. Abra o OpenCode e selecione qualquer modelo OpenAGY no seletor:"
echo "    - openagy/gemini-3.8-flash-high"
echo "    - openagy/gemini-3.1-pro-high"
echo "    - openagy/claude-sonnet-5-5-high"
echo "============================================================"
