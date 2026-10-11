import os
import shutil
import sys
from pathlib import Path

def find_default_agy_bin() -> str:
    """Discovers the Antigravity CLI binary across Linux, macOS, and Windows."""
    env_bin = os.getenv("OPENAGY_AGY_BIN")
    if env_bin:
        return env_bin

    is_windows = (sys.platform == "win32" or os.name == "nt")
    home = Path.home()

    # 1. Search PATH (prioritize .exe over .cmd/.bat)
    names = ["agy.exe", "agy.cmd", "agy.bat", "agy"] if is_windows else ["agy"]
    for name in names:
        found = shutil.which(name)
        if found:
            if is_windows and found.lower().endswith((".cmd", ".bat")):
                exe_candidate = os.path.splitext(found)[0] + ".exe"
                if os.path.exists(exe_candidate):
                    return exe_candidate
            return found

    # 2. Known default installation directories
    candidates: list[Path] = []
    if is_windows:
        local_app_data = os.getenv("LOCALAPPDATA")
        app_data = os.getenv("APPDATA")
        program_files = os.getenv("ProgramFiles")
        if local_app_data:
            candidates.extend([
                Path(local_app_data) / "Programs" / "antigravity" / "bin" / "agy.exe",
                Path(local_app_data) / "antigravity-cli" / "bin" / "agy.exe",
                Path(local_app_data) / "Microsoft" / "WinGet" / "Links" / "agy.exe",
            ])
        candidates.extend([
            home / ".local" / "bin" / "agy.exe",
            home / ".gemini" / "antigravity-cli" / "bin" / "agy.exe",
            home / "bin" / "agy.exe",
            home / ".local" / "bin" / "agy.cmd",
            home / ".local" / "bin" / "agy",
        ])
        if program_files:
            candidates.append(Path(program_files) / "Antigravity" / "agy.exe")
    else:
        # Linux & macOS
        candidates.extend([
            home / ".local" / "bin" / "agy",
            home / ".gemini" / "antigravity-cli" / "bin" / "agy",
            Path("/usr/local/bin/agy"),
            Path("/usr/bin/agy"),
            Path("/opt/homebrew/bin/agy"),
            home / "bin" / "agy",
        ])

    for c in candidates:
        if c.exists():
            str_c = str(c)
            if is_windows and str_c.lower().endswith((".cmd", ".bat")):
                exe_candidate = os.path.splitext(str_c)[0] + ".exe"
                if os.path.exists(exe_candidate):
                    return exe_candidate
            return str_c

    # 3. Fallback path if not yet installed
    if is_windows:
        return str(home / ".local" / "bin" / "agy.exe")
    return str(home / ".local" / "bin" / "agy")

class Config:
    HOST: str = os.getenv("OPENAGY_HOST", "127.0.0.1")
    PORT: int = int(os.getenv("OPENAGY_PORT", "8080"))
    
    # API Key validated against incoming OpenCode requests
    # Set to empty or None to accept any non-empty bearer token
    API_KEY: str = os.getenv("OPENAGY_API_KEY", "openagy-key")
    REQUIRE_API_KEY: bool = os.getenv("OPENAGY_REQUIRE_KEY", "false").lower() in ("true", "1", "yes")

    # Paths to Antigravity credentials
    HOME = Path.home()
    PRIMARY_TOKEN_PATH: Path = HOME / ".gemini" / "antigravity-cli" / "antigravity-oauth-token"
    FALLBACK_TOKEN_PATH: Path = HOME / ".gemini" / "oauth_creds.json"
    JETSKI_TOKEN_PATH: Path = HOME / ".gemini" / "jetski-standalone-oauth-token"

    # Antigravity CLI binary path (resolved cross-platform)
    AGY_BIN: str = find_default_agy_bin()

    # Backend endpoints used by Antigravity CLI
    # Antigravity uses cloudcode-pa (production) and daily-cloudcode-pa (staging)
    UPSTREAM_URL: str = os.getenv(
        "OPENAGY_UPSTREAM_URL",
        "https://cloudcode-pa.googleapis.com/v1internal:streamGenerateContent?alt=sse"
    )
    BACKUP_UPSTREAM_URL: str = "https://daily-cloudcode-pa.googleapis.com/v1internal:streamGenerateContent?alt=sse"

    LOAD_CODE_ASSIST_URL: str = "https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist"
    BACKUP_LOAD_CODE_ASSIST_URL: str = "https://daily-cloudcode-pa.googleapis.com/v1internal:loadCodeAssist"

    # Default engine: "cli" connects to the local Antigravity binary (agy)
    ENGINE: str = os.getenv("OPENAGY_ENGINE", "cli")

    # Logging level
    LOG_LEVEL: str = os.getenv("OPENAGY_LOG_LEVEL", "INFO")

config = Config()
