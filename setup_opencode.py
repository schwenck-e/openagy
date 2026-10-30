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

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ANTIGRAVITY_SETTINGS_PATH = Path.home() / ".gemini" / "antigravity-cli" / "settings.json"

MODELS_CATALOG = {
    "gemini-4-argon-low": {
        "name": "Gemini 4 Argon (Low)",
        "limit": {
            "context": 1048576,
            "output": 8192
        }
    },
    "gemini-4-argon-medium": {
        "name": "Gemini 4 Argon (Medium)",
        "limit": {
            "context": 1048576,
            "output": 8192
        }
    },
    "gemini-4-argon-high": {
        "name": "Gemini 4 Argon (High)",
        "limit": {
            "context": 1048576,
            "output": 8192
        }
    },
    "gemini-3.8-flash-low": {
        "name": "Gemini 3.8 Flash (Low)",
        "limit": {
            "context": 1048576,
            "output": 8192
        }
    },
    "gemini-3.8-flash-medium": {
        "name": "Gemini 3.8 Flash (Medium)",
        "limit": {
            "context": 1048576,
            "output": 8192
        }
    },
    "gemini-3.8-flash-high": {
        "name": "Gemini 3.8 Flash (High)",
        "limit": {
            "context": 1048576,
            "output": 8192
        }
    },
    "claude-sonnet-5-5-low": {
        "name": "Claude Sonnet 5.5 (Low)",
        "limit": {
            "context": 200000,
            "output": 8192
        }
    },
    "claude-sonnet-5-5-medium": {
        "name": "Claude Sonnet 5.5 (Medium)",
        "limit": {
            "context": 200000,
            "output": 8192
        }
    },
    "claude-sonnet-5-5-high": {
        "name": "Claude Sonnet 5.5 (High)",
        "limit": {
            "context": 200000,
            "output": 8192
        }
    },
    "claude-opus-5-5-low": {
        "name": "Claude Opus 5.5 (Low)",
        "limit": {
            "context": 200000,
            "output": 8192
        }
    },
    "claude-opus-5-5-medium": {
        "name": "Claude Opus 5.5 (Medium)",
        "limit": {
            "context": 200000,
            "output": 8192
        }
    },
    "claude-opus-5-5-high": {
        "name": "Claude Opus 5.5 (High)",
        "limit": {
            "context": 200000,
            "output": 8192
        }
    },
    "gpt-oss-120b-medium": {
        "name": "GPT-OSS 120B (Medium)",
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

def enable_desktop_model_visibility():
    """Habilita a visibilidade de todos os modelos do OpenAGY no OpenCode 2 Desktop (drafts.sqlite)."""
    import sqlite3
    import glob

    candidate_dirs = []
    if sys.platform == "win32" or os.name == "nt":
        appdata = os.getenv("APPDATA")
        if appdata:
            candidate_dirs.append(Path(appdata) / "ai.opencode.desktop")
    elif sys.platform == "darwin":
        candidate_dirs.append(Path.home() / "Library" / "Application Support" / "ai.opencode.desktop")
    else:
        xdg = os.getenv("XDG_CONFIG_HOME")
        if xdg:
            candidate_dirs.append(Path(xdg) / "ai.opencode.desktop")
        candidate_dirs.append(Path.home() / ".config" / "ai.opencode.desktop")

    for d in candidate_dirs:
        db_path = d / "drafts.sqlite"
        if not db_path.exists():
            continue
        try:
            conn = sqlite3.connect(str(db_path), timeout=5.0)
            cur = conn.cursor()
            row = cur.execute(
                "SELECT value FROM state WHERE name = ? AND key = ?",
                ("opencode.global.dat", "model")
            ).fetchone()
            if row and row[0]:
                state_obj = json.loads(row[0])
            else:
                state_obj = {"user": [], "recent": [], "favorite": [], "variant": {}}

            user_list = state_obj.get("user", [])
            # Preserve non-openagy models and replace openagy models with full catalog enabled
            filtered_user = [
                entry for entry in user_list
                if not (isinstance(entry, dict) and entry.get("providerID") == "openagy")
            ]
            for m_id in MODELS_CATALOG.keys():
                filtered_user.append({
                    "providerID": "openagy",
                    "modelID": m_id,
                    "visibility": "show"
                })
            state_obj["user"] = filtered_user

            now_ms = int(time.time() * 1000)
            cur.execute(
                """
                INSERT INTO state (name, key, value, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(name, key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                ("opencode.global.dat", "model", json.dumps(state_obj, separators=(",", ":")), now_ms)
            )
            conn.commit()
            conn.close()
            print(f"👁️ Visibilidade dos modelos ativada no OpenCode Desktop:\n   {db_path}")
        except Exception as e:
            print(f"[!] Aviso: Não foi possível atualizar visibilidade em {db_path}: {e}")

def reload_opencode():
    """Tenta recarregar a configuração do OpenCode daemon se o CLI estiver instalado."""
    import glob
    candidates = [
        shutil.which("opencode"),
        str(Path.home() / ".bun" / "bin" / "opencode"),
        "/usr/local/bin/opencode",
        "/opt/homebrew/bin/opencode"
    ]
    appdata = os.getenv("APPDATA")
    if appdata:
        candidates.extend(glob.glob(os.path.join(appdata, "ai.opencode.desktop", "cli", "*", "opencode-cli*")))
    for c in candidates:
        if c and os.path.exists(c):
            try:
                res = subprocess.run([c, "reload"], capture_output=True, text=True, timeout=5)
                if res.returncode == 0:
                    print(f"🔄 OpenCode daemon recarregado automaticamente ({os.path.basename(c)} reload).")
            except Exception:
                pass

def setup_opencode(
    port: int = 8080,
    api_key: str = "openagy-key",
    default_model: str = "openagy/gemini-4-argon-medium",
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
    enable_desktop_model_visibility()
    reload_opencode()

    print("\n" + "=" * 60)
    print(" 🎉 Configuração concluída com sucesso!")
    print(" Se o OpenCode estiver aberto na interface gráfica, recarregue a janela.")
    print("=" * 60)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Configure OpenCode to use OpenAGY")
    parser.add_argument("--port", type=int, default=8080, help="Bridge port (default: 8080)")
    parser.add_argument("--key", type=str, default="openagy-key", help="API Key (default: openagy-key)")
    parser.add_argument("--default-model", type=str, default="openagy/gemini-4-argon-medium",
                        help="Default model for OpenCode and subagents (default: openagy/gemini-4-argon-medium)")
    parser.add_argument("--config", type=str, default=None, help="Explicit path to opencode.json")
    args = parser.parse_args()
    setup_opencode(port=args.port, api_key=args.key, default_model=args.default_model, custom_config=args.config)
