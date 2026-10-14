import time
from typing import Dict, Any, List

AVAILABLE_MODELS: List[Dict[str, Any]] = [
    {
        "id": "gemini-3.8-flash-high",
        "name": "Gemini 3.8 Flash (High Reasoning)",
        "description": "Default flagship fast reasoning model on Antigravity",
        "context_window": 1048576,
    },
    {
        "id": "gemini-3.8-flash-medium",
        "name": "Gemini 3.8 Flash (Medium Reasoning)",
        "description": "Balanced reasoning model",
        "context_window": 1048576,
    },
    {
        "id": "gemini-3.8-flash-low",
        "name": "Gemini 3.8 Flash (Low Reasoning)",
        "description": "Lowest latency flash model",
        "context_window": 1048576,
    },
    {
        "id": "gemini-3.7-flash-high",
        "name": "Gemini 3.7 Flash (High)",
        "description": "Gemini 3.7 Flash reasoning model",
        "context_window": 1048576,
    },
    {
        "id": "gemini-3.1-pro-high",
        "name": "Gemini 3.1 Pro (High)",
        "description": "Gemini 3.1 Pro deep reasoning model",
        "context_window": 2097152,
    },
    {
        "id": "gemini-3.1-pro-low",
        "name": "Gemini 3.1 Pro (Low)",
        "description": "Gemini 3.1 Pro fast model",
        "context_window": 2097152,
    },
    {
        "id": "claude-sonnet-5-5-high",
        "name": "Claude Sonnet 5.5 (High)",
        "description": "Anthropic Claude Sonnet 5.5 via Antigravity backend",
        "context_window": 200000,
    },
    {
        "id": "claude-opus-5-5-high",
        "name": "Claude Opus 5.5 (High)",
        "description": "Anthropic Claude Opus 5.5 via Antigravity backend",
        "context_window": 200000,
    },
    {
        "id": "gpt-oss-120b-medium",
        "name": "GPT-OSS 120B (Medium)",
        "description": "Open weights flagship model on Antigravity",
        "context_window": 128000,
    },
]

# Aliases to gracefully redirect common model names from various tools to Antigravity models
MODEL_ALIASES: Dict[str, str] = {
    "gemini-3.8-flash": "gemini-3.8-flash-high",
    "gemini-3.8-pro": "gemini-3.1-pro-high",
    "gemini-2.5-pro": "gemini-3.1-pro-high",
    "gemini-2.5-flash": "gemini-3.8-flash-high",
    "gemini-2.0-flash": "gemini-3.8-flash-low",
    "claude-3-7-sonnet": "claude-sonnet-5-5-high",
    "claude-3-5-sonnet": "claude-sonnet-5-5-high",
    "claude-3-opus": "claude-opus-5-5-high",
    "gpt-4o": "gemini-3.8-flash-high",
    "gpt-4o-mini": "gemini-3.8-flash-low",
    "o1": "gemini-3.1-pro-high",
    "o3-mini": "gemini-3.8-flash-high",
}

def resolve_model_name(requested_model: str) -> str:
    """Resolves an alias or provider-prefixed name to the canonical Antigravity model ID."""
    if not requested_model:
        return "gemini-3.8-flash-high"
    
    clean_name = requested_model.strip()
    if clean_name.startswith("openagy/"):
        clean_name = clean_name[8:]
    elif "/" in clean_name:
        clean_name = clean_name.split("/", 1)[1]

    if clean_name in MODEL_ALIASES:
        return MODEL_ALIASES[clean_name]
    
    # Check case-insensitive match
    lower = clean_name.lower()
    for model in AVAILABLE_MODELS:
        if model["id"].lower() == lower:
            return model["id"]
            
    for alias, target in MODEL_ALIASES.items():
        if alias.lower() == lower:
            return target
            
    # Default to requested name if already matching an Antigravity model format
    return clean_name

def get_openai_models_response() -> Dict[str, Any]:
    """Returns the /v1/models response in standard OpenAI JSON format."""
    now = int(time.time())
    data = []
    for m in AVAILABLE_MODELS:
        data.append({
            "id": m["id"],
            "object": "model",
            "created": now,
            "owned_by": "google-antigravity",
            "permission": [],
            "root": m["id"],
            "parent": None,
        })
    # Also expose popular aliases
    for alias in ["gpt-4o", "claude-3-7-sonnet", "gemini-2.5-pro"]:
        data.append({
            "id": alias,
            "object": "model",
            "created": now,
            "owned_by": "google-antigravity",
            "permission": [],
            "root": alias,
            "parent": None,
        })
    return {
        "object": "list",
        "data": data,
    }
