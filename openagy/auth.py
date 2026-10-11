import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple
import urllib.request
import urllib.parse
from openagy.config import config

logger = logging.getLogger("openagy.auth")

class AuthManager:
    """
    Manages OAuth tokens loaded from Antigravity's local session files.
    Ensures that requests to Google Antigravity backends use the valid access_token.
    """
    
    def __init__(self):
        self._cached_token: Optional[str] = None
        self._token_expiry: float = 0
        self._token_path: Path = config.PRIMARY_TOKEN_PATH
        self._cached_project_id: Optional[str] = None

    def get_token_paths(self) -> list[Path]:
        return [
            config.PRIMARY_TOKEN_PATH,
            config.FALLBACK_TOKEN_PATH,
            config.JETSKI_TOKEN_PATH,
        ]

    def load_token_data(self) -> Tuple[Optional[dict], Optional[Path]]:
        for path in self.get_token_paths():
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        return data, path
                except Exception as e:
                    logger.warning(f"Failed to read token file {path}: {e}")
        return None, None

    def get_access_token(self, force_refresh: bool = False) -> str:
        """
        Retrieves a valid access token. Reads directly from the local Antigravity
        token store so any refresh performed by the CLI or IDE is picked up immediately.
        """
        now = time.time()
        
        # If cache is valid and not forcing refresh, return it
        if not force_refresh and self._cached_token and (self._token_expiry - now > 60):
            return self._cached_token

        data, path = self.load_token_data()
        if not data:
            raise RuntimeError(
                f"Antigravity OAuth token not found in any expected location:\n"
                f"  - {config.PRIMARY_TOKEN_PATH}\n"
                f"  - {config.FALLBACK_TOKEN_PATH}\n"
                f"Please ensure you are authenticated in the Antigravity CLI ('agy')."
            )

        access_token = None
        refresh_token = None
        expiry_ts = 0

        # Pattern 1: antigravity-oauth-token format
        if "token" in data and isinstance(data["token"], dict):
            token_dict = data["token"]
            access_token = token_dict.get("access_token")
            refresh_token = token_dict.get("refresh_token")
            expiry_str = token_dict.get("expiry")
            if expiry_str:
                try:
                    # ISO format timestamp parsing
                    dt = datetime.fromisoformat(expiry_str)
                    expiry_ts = dt.timestamp()
                except Exception:
                    expiry_ts = now + 1800
        # Pattern 2: oauth_creds.json format
        elif "access_token" in data:
            access_token = data.get("access_token")
            refresh_token = data.get("refresh_token")
            expiry_date = data.get("expiry_date")
            if expiry_date:
                expiry_ts = float(expiry_date) / 1000.0 if float(expiry_date) > 1e11 else float(expiry_date)

        if not access_token:
            raise RuntimeError(f"Unable to parse access_token from {path}")

        # Check if expired and refresh_token exists
        if (expiry_ts and expiry_ts <= now + 30) or force_refresh:
            logger.info("Access token is expired or expiring soon, attempting refresh...")
            new_token = self._refresh_oauth_token(refresh_token, path, data)
            if new_token:
                access_token = new_token
                expiry_ts = time.time() + 3500

        self._cached_token = access_token
        self._token_expiry = expiry_ts or (now + 1800)
        return access_token

    def get_project_id(self) -> Optional[str]:
        """
        Retrieves project ID from cache, environment variables, or token files.
        """
        if self._cached_project_id:
            return self._cached_project_id

        # 1. Check environment variables
        env_proj = os.getenv("OPENAGY_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
        if env_proj:
            self._cached_project_id = env_proj
            return env_proj

        # 2. Check token data JSON
        data, _ = self.load_token_data()
        if data:
            for key in ["project_id", "project", "cloudaicompanionProject", "projectId"]:
                if key in data and data[key]:
                    self._cached_project_id = str(data[key])
                    return self._cached_project_id
            if "token" in data and isinstance(data["token"], dict):
                for key in ["project_id", "project", "cloudaicompanionProject", "projectId"]:
                    if key in data["token"] and data["token"][key]:
                        self._cached_project_id = str(data["token"][key])
                        return self._cached_project_id

        # 3. Check other potential gemini config files
        gemini_dir = config.HOME / ".gemini"
        for candidate_file in [gemini_dir / "projects.json", gemini_dir / "current_project.json", gemini_dir / "antigravity-cli" / "settings.json"]:
            if candidate_file.exists():
                try:
                    with open(candidate_file, "r", encoding="utf-8") as f:
                        cfg_data = json.load(f)
                        for key in ["project_id", "project", "cloudaicompanionProject", "active_project"]:
                            if key in cfg_data and cfg_data[key]:
                                self._cached_project_id = str(cfg_data[key])
                                return self._cached_project_id
                except Exception:
                    pass

        return None

    async def resolve_project_id(self, token: str) -> Optional[str]:
        """
        Resolves the user's Google Cloud project ID. If not found locally,
        queries the v1internal:loadCodeAssist endpoint to discover cloudaicompanionProject.
        """
        existing = self.get_project_id()
        if existing:
            return existing

        import httpx
        endpoints = [
            config.LOAD_CODE_ASSIST_URL,
            config.BACKUP_LOAD_CODE_ASSIST_URL,
        ]
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "Antigravity-CLI/2.0 (macOS; arm64)",
        }
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            for ep in endpoints:
                try:
                    logger.info(f"Querying {ep} to resolve cloudaicompanionProject...")
                    resp = await client.post(ep, headers=headers, json={"metadata": {}})
                    if resp.status_code == 200:
                        res_data = resp.json()
                        proj = res_data.get("cloudaicompanionProject") or res_data.get("project")
                        if proj:
                            self._cached_project_id = str(proj)
                            logger.info(f"Successfully resolved project ID: {self._cached_project_id}")
                            return self._cached_project_id
                        else:
                            logger.debug(f"{ep} response did not contain project ID: {res_data}")
                    else:
                        logger.debug(f"{ep} returned status {resp.status_code}: {resp.text[:200]}")
                except Exception as e:
                    logger.debug(f"Failed to query {ep} for project discovery: {e}")

        return None

    def _refresh_oauth_token(self, refresh_token: Optional[str], path: Path, full_data: dict) -> Optional[str]:
        """
        Attempts to refresh the token using Google OAuth endpoint if refresh_token is present.
        If refresh fails, attempts to re-read the file in case agy refreshed it.
        """
        if not refresh_token:
            return None

        # Google Cloud SDK / Cloud Code client ID fallback
        client_ids = [
            # Standard Cloud Code / gcloud client ID
            ("764086051850-6qr4p6gpi6hn506pt8ejuq83di341hur.apps.googleusercontent.com", None),
        ]

        for client_id, client_secret in client_ids:
            try:
                req_data = {
                    "client_id": client_id,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                }
                if client_secret:
                    req_data["client_secret"] = client_secret

                req_body = urllib.parse.urlencode(req_data).encode("utf-8")
                req = urllib.request.Request(
                    "https://oauth2.googleapis.com/token",
                    data=req_body,
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    if resp.status == 200:
                        res = json.loads(resp.read().decode("utf-8"))
                        new_access = res.get("access_token")
                        if new_access:
                            logger.info("Successfully refreshed OAuth token via Google OAuth endpoint.")
                            # Update local file cache if writable
                            self._update_saved_token(path, full_data, new_access, res.get("expires_in", 3600))
                            return new_access
            except Exception as e:
                logger.debug(f"Direct OAuth refresh failed with client_id {client_id}: {e}")

        logger.info("Direct refresh not possible; checking if agy session was updated on disk.")
        return None

    def _update_saved_token(self, path: Path, full_data: dict, new_access: str, expires_in: int):
        try:
            if "token" in full_data and isinstance(full_data["token"], dict):
                full_data["token"]["access_token"] = new_access
                new_expiry = datetime.fromtimestamp(time.time() + expires_in, timezone.utc).isoformat()
                full_data["token"]["expiry"] = new_expiry
            elif "access_token" in full_data:
                full_data["access_token"] = new_access
                full_data["expiry_date"] = int((time.time() + expires_in) * 1000)

            with open(path, "w", encoding="utf-8") as f:
                json.dump(full_data, f, indent=2)
            logger.info(f"Updated token file at {path}")
        except Exception as e:
            logger.warning(f"Could not write refreshed token back to {path}: {e}")

auth_manager = AuthManager()
