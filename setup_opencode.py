#!/usr/bin/env python3
"""
Setup and Configuration Utility for OpenAGY in OpenCode.
Configures OpenCode (on Linux, Windows, or macOS) to register OpenAGY as an OpenAI-compatible provider
with all required model limits, schemas for the chat model selector, and sets OpenAGY as the default model
so subagents seamlessly inherit the Antigravity backend.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

ANTIGRAVITY_SETTINGS_PATH = Path.home() / ".gemini" / "antigravity-cli" / "settings.json"

MODELS_CATALOG = {
    "gemini-3.8-flash-low": {
        "name": "Gemini 3.8 Flash Low (Fast / Low Latency)",
        "limit": {
            "context": 1048576,
            "output": 8192
        }
    },
    "gemini-3.8-flash-medium": {
        "name": "Gemini 3.8 Flash Medium (Balanced)",
        "limit": {
            "context": 1048576,
            "output": 8192
        }
    },
    "gemini-3.8-flash-high": {
        "name": "Gemini 3.8 Flash High (Deep Reasoning)",
        "limit": {
            "context": 1048576,
            "output": 8192
        }
    },
    "gemini-3.1-pro-high": {
        "name": "Gemini 3.1 Pro High (Antigravity)",
        "limit": {
            "context": 2097152,
            "output": 8192
        }
    },
    "claude-sonnet-5-5-high": {
        "name": "Claude Sonnet 5.5 (Antigravity)",
        "limit": {
            "context": 200000,
            "output": 8192
        }
    },
    "gpt-oss-120b-medium": {
        "name": "GPT-OSS 120B (Antigravity)",
        "limit": {
            "context": 128000,
            "output": 8192
        }
    }
}

def discover_opencode_config_paths(custom_path: Optional[str] = None) -> List[Path]:
    """Discovers candidate paths for opencode.json and opencode.jsonc across Windows, Linux, and macOS."""
    if custom_path:
        return [Path(custom_path)]

    env_path = os.getenv("OPENCODE_CONFIG_PATH")
    if env_path:
        return [Path(env_path)]

    is_windows = (sys.platform == "win32" or os.name == "nt")
    dirs: List[Path] = []

    if is_windows:
        appdata = os.getenv("APPDATA")
        if appdata:
            dirs.append(Path(appdata) / "opencode")
        dirs.append(Path.home() / ".config" / "opencode")
    else:
        # Linux & macOS
        xdg_config = os.getenv("XDG_CONFIG_HOME")
        if xdg_config:
            dirs.append(Path(xdg_config) / "opencode")
        dirs.append(Path.home() / ".config" / "opencode")
        if sys.platform == "darwin":
            dirs.append(Path.home() / "Library" / "Application Support" / "opencode")

    files: List[Path] = []
    for d in dirs:
        p_json = d / "opencode.json"
        p_jsonc = d / "opencode.jsonc"
        if p_json.exists():
            files.append(p_json)
        if p_jsonc.exists():
            files.append(p_jsonc)

    if files:
        return list(dict.fromkeys(files))

    # Fallback to standard primary path
    primary_dir = dirs[0] if dirs else (Path.home() / ".config" / "opencode")
    return [primary_dir / "opencode.json"]

def configure_antigravity_settings():
    """Garante que ~/.gemini/antigravity-cli/settings.json existe de forma segura."""
    try:
        ANTIGRAVITY_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        if not ANTIGRAVITY_SETTINGS_PATH.exists():
            with open(ANTIGRAVITY_SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump({}, f, indent=2)
    except Exception as e:
        print(f"[!] Aviso: Não foi possível verificar settings.json do Antigravity: {e}")

def update_single_config(config_path: Path, port: int, api_key: str, default_model: str):
    config_dir = config_path.parent
    config_dir.mkdir(parents=True, exist_ok=True)

    config = {}
    if config_path.exists():
        backup_path = config_dir / f"{config_path.name}.bak-{int(time.time())}"
        try:
            shutil.copy2(config_path, backup_path)
            print(f"📦 Backup criado em:\n   {backup_path}")
        except Exception:
            pass
        
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception as e:
            print(f"[!] Aviso: Não foi possível ler {config_path} como JSON ({e}). Criando nova base.")
            config = {}

    # 1. Preservar o schema padrão do OpenCode
    if "$schema" not in config:
        config["$schema"] = "https://opencode.ai/config.json"

    # 2. Configurar modelo padrão do OpenCode (garante que subagentes herdem o OpenAGY)
    config["model"] = default_model

    # 3. Preservar MCP servers existentes
    if "mcp" not in config:
        config["mcp"] = {}

    # 4. Estrutura do provedor OpenAGY
    if "provider" not in config or not isinstance(config["provider"], dict):
        config["provider"] = {}

    config["provider"]["openagy"] = {
        "name": "OpenAGY",
        "npm": "@ai-sdk/openai-compatible",
        "options": {
            "baseURL": f"http://127.0.0.1:{port}/v1",
            "apiKey": api_key,
            "timeout": 600000,
            "headerTimeout": 600000,
            "chunkTimeout": 900000
        },
        "models": MODELS_CATALOG
    }

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    print(f"✅ Arquivo atualizado com sucesso:\n   {config_path}")

def reload_opencode():
    """Tenta recarregar a configuração do OpenCode daemon se o CLI estiver instalado."""
    candidates = [
        shutil.which("opencode"),
        str(Path.home() / ".bun" / "bin" / "opencode"),
        "/usr/local/bin/opencode",
        "/opt/homebrew/bin/opencode"
    ]
    for c in candidates:
        if c and os.path.exists(c):
            try:
                res = subprocess.run([c, "reload"], capture_output=True, text=True, timeout=5)
                if res.returncode == 0:
                    print("🔄 OpenCode daemon recarregado automaticamente (opencode reload).")
                return
            except Exception:
                pass

def setup_opencode(
    port: int = 8080,
    api_key: str = "openagy-key",
    default_model: str = "openagy/gemini-3.8-flash-medium",
    custom_config: Optional[str] = None
):
    print("=" * 60)
    print(" 🛠️ Configurando OpenCode para integração com OpenAGY")
    print(f"    Sistema Operacional: {sys.platform}")
    print("=" * 60)

    target_paths = discover_opencode_config_paths(custom_config)
    for p in target_paths:
        update_single_config(p, port, api_key, default_model)

    print(f"\nProvedor Registrado:")
    print(f"   Nome: OpenAGY")
    print(f"   NPM: @ai-sdk/openai-compatible")
    print(f"   BaseURL: http://127.0.0.1:{port}/v1")
    print(f"   API Key: {api_key}")
    print(f"   Modelo Padrão: {default_model}")
    print("\nModelos Disponíveis no Seletor do Chat:")
    for m_id, m_data in MODELS_CATALOG.items():
        ctx = m_data["limit"]["context"]
        print(f"   • openagy/{m_id} ({m_data['name']}) [Contexto: {ctx:,} tokens]")

    configure_antigravity_settings()
    reload_opencode()

    print("\n" + "=" * 60)
    print(" 🎉 Configuração concluída com sucesso!")
    print(" Se o OpenCode estiver aberto na interface gráfica, recarregue a janela.")
    print("=" * 60)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Configure OpenCode to use OpenAGY")
    parser.add_argument("--port", type=int, default=8080, help="Bridge port (default: 8080)")
    parser.add_argument("--key", type=str, default="openagy-key", help="API Key (default: openagy-key)")
    parser.add_argument("--default-model", type=str, default="openagy/gemini-3.8-flash-medium",
                        help="Default model for OpenCode and subagents (default: openagy/gemini-3.8-flash-medium)")
    parser.add_argument("--config", type=str, default=None, help="Explicit path to opencode.json")
    args = parser.parse_args()
    setup_opencode(port=args.port, api_key=args.key, default_model=args.default_model, custom_config=args.config)
