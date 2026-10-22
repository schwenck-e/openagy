#!/usr/bin/env bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# Detect Python
PYTHON_BIN=""
if command -v python3 &> /dev/null; then
    PYTHON_BIN="python3"
elif command -v python &> /dev/null; then
    if python -c "import sys; sys.exit(0 if sys.version_info[0] >= 3 else 1)" 2>/dev/null; then
        PYTHON_BIN="python"
    fi
fi

if [ -z "$PYTHON_BIN" ] && [ ! -f "venv/bin/python" ]; then
    echo "❌ Python 3 é obrigatório, mas não foi encontrado no seu PATH."
    exit 1
fi

# Set up virtual environment if not present
if [ ! -d "venv" ]; then
    echo "📦 Criando ambiente virtual..."
    "$PYTHON_BIN" -m venv venv || true
fi

if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    python -m pip install -q -r requirements.txt
    echo "🚀 Iniciando OpenAGY Bridge..."
    exec python main.py "$@"
else
    "$PYTHON_BIN" -m pip install -q -r requirements.txt
    echo "🚀 Iniciando OpenAGY Bridge..."
    exec "$PYTHON_BIN" main.py "$@"
fi
