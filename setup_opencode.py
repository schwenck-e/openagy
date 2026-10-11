#!/usr/bin/env python3
"""
Setup and Configuration Utility for OpenAGY in OpenCode.
Configures OpenCode (on Linux, Windows, or macOS) to register OpenAGY as an OpenAI-compatible provider
with all required model limits and schemas for the chat model selector.
"""

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import List, Optional

ANTIGRAVITY_SETTINGS_PATH = Path.home() / ".gemini" / "antigravity-cli" / "settings.json"

MODELS_CATALOG = {
    "gemini-3.8-flash-high": {
        "name": "Gemini 3.8 Flash High (Antigravity)",
        "limit": {
            "context": 1048576,
            "output": 8192
        }
    },
    "gemini-3.8-flash-medium": {
        "name": "Gemini 3.8 Flash Medium (Antigravity)",
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
    """
    Discovers candidate paths for opencode.json across Windows, Linux, and macOS.
    """
    if custom_path:
        return [Path(custom_path)]

    env_path = os.getenv("OPENCODE_CONFIG_PATH")
    if env_path:
        return [Path(env_path)]

    is_windows = (sys.platform == "win32" or os.name == "nt")
    candidates: List[Path] = []

    if is_windows:
        appdata = os.getenv("APPDATA")
        if appdata:
            candidates.append(Path(appdata) / "opencode" / "opencode.json")
        candidates.append(Path.home() / ".config" / "opencode" / "opencode.json")
    else:
        # Linux & macOS
        xdg_config = os.getenv("XDG_CONFIG_HOME")
        if xdg_config:
            candidates.append(Path(xdg_config) / "opencode" / "opencode.json")
        candidates.append(Path.home() / ".config" / "opencode" / "opencode.json")
        if sys.platform == "darwin":
            candidates.append(Path.home() / "Library" / "Application Support" / "opencode" / "opencode.json")

    # If any candidate already exists on disk, configure all existing ones
    existing = [p for p in candidates if p.exists()]
    if existing:
        return existing

    # If none exist yet, return candidate paths (primary path first)
    return candidates

def configure_antigravity_permissions():
    """Garante que ~/.gemini/antigravity-cli/settings.json tenha permissões liberadas para o jetski."""
    try:
        ANTIGRAVITY_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        if ANTIGRAVITY_SETTINGS_PATH.exists():
            with open(ANTIGRAVITY_SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)

        perms = data.get("permissions", {})
        allow = perms.get("allow", [])

        needed = ["command(*)", "command()", "read_file(*)", "edit_file(*)", "*"]
        modified = False
        for item in needed:
            if item not in allow:
                allow.append(item)
                modified = True

        if modified:
            perms["allow"] = allow
            data["permissions"] = perms
            with open(ANTIGRAVITY_SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            print(f"🔓 Permissões automáticas pré-autorizadas em: {ANTIGRAVITY_SETTINGS_PATH}")
    except Exception as e:
        print(f"[!] Aviso: Não foi possível atualizar settings.json do Antigravity: {e}")

def update_single_config(config_path: Path, port: int, api_key: str):
    config_dir = config_path.parent
    config_dir.mkdir(parents=True, exist_ok=True)

    config = {}
    if config_path.exists():
        backup_path = config_dir / f"opencode.json.bak-{int(time.time())}"
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

    # 2. Remoção de chaves inválidas que causam crash ou erro de validação
    # No OpenCode, a chave raiz 'model' não deve existir se não for um enum válido de models.dev
    if "model" in config:
        print("🧹 Removendo chave raiz 'model' legada para evitar erro de validação no OpenCode...")
        del config["model"]

    # 3. Preservar MCP servers existentes (ex: zrq-engine)
    if "mcp" not in config:
        config["mcp"] = {}

    # 4. Estrutura do provedor
    if "provider" not in config or not isinstance(config["provider"], dict):
        config["provider"] = {}

    # Registrar o provedor com @ai-sdk/openai-compatible e limites obrigatórios para cada modelo
    config["provider"]["openagy"] = {
        "name": "OpenAGY",
        "npm": "@ai-sdk/openai-compatible",
        "options": {
            "baseURL": f"http://127.0.0.1:{port}/v1",
            "apiKey": api_key
        },
        "models": MODELS_CATALOG
    }

    # Salvar opencode.json formatado
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    print(f"✅ Arquivo atualizado com sucesso:\n   {config_path}")

def setup_opencode(port: int = 8080, api_key: str = "openagy-key", custom_config: Optional[str] = None):
    print("=" * 60)
    print(" 🛠️ Configurando OpenCode para integração com OpenAGY")
    print(f"    Sistema Operacional: {sys.platform}")
    print("=" * 60)

    target_paths = discover_opencode_config_paths(custom_config)
    for p in target_paths:
        update_single_config(p, port, api_key)

    print(f"\nProvedor Registrado:")
    print(f"   Nome: OpenAGY")
    print(f"   NPM: @ai-sdk/openai-compatible")
    print(f"   BaseURL: http://127.0.0.1:{port}/v1")
    print(f"   API Key: {api_key}")
    print("\nModelos Disponíveis no Seletor do Chat:")
    for m_id, m_data in MODELS_CATALOG.items():
        ctx = m_data["limit"]["context"]
        print(f"   • openagy/{m_id} ({m_data['name']}) [Contexto: {ctx:,} tokens]")

    # 5. Configurar permissões do jetski no Antigravity
    configure_antigravity_permissions()

    print("\n" + "=" * 60)
    print(" 🎉 Configuração concluída com sucesso!")
    print(" Se o OpenCode estiver aberto, reinicie-o para carregar os novos modelos.")
    print("=" * 60)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Configure OpenCode to use OpenAGY")
    parser.add_argument("--port", type=int, default=8080, help="Bridge port (default: 8080)")
    parser.add_argument("--key", type=str, default="openagy-key", help="API Key (default: openagy-key)")
    parser.add_argument("--config", type=str, default=None, help="Explicit path to opencode.json")
    args = parser.parse_args()
    setup_opencode(port=args.port, api_key=args.key, custom_config=args.config)
