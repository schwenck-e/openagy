import collections
import json
import logging
import time
import uuid
from typing import Optional, Dict, Any
from fastapi import FastAPI, Request, HTTPException, Security, status
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from openagy.config import config
from openagy.models import get_openai_models_response
from openagy.engines.cloudcode_engine import CloudCodeEngine
from openagy.engines.cli_engine import CliEngine
from openagy.auth import auth_manager

logger = logging.getLogger("openagy.server")

# File logger for persistent diagnostic tracking
try:
    fh = logging.FileHandler("openagy.log", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logging.getLogger("openagy").addHandler(fh)
    logging.getLogger("openagy.engine.cli").addHandler(fh)
except Exception:
    pass

app = FastAPI(
    title="OpenAGY - OpenCode to Antigravity Bridge",
    description="Local OpenAI-compatible API bridge translating OpenCode requests into Google Antigravity executions.",
    version="0.1.0"
)

# CORS middleware to allow connections from any local client
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer(auto_error=False)

cloudcode_engine = CloudCodeEngine()
cli_engine = CliEngine()

# Diagnostic request trackers
REQUEST_HISTORY = collections.deque(maxlen=30)
ACTIVE_REQUESTS: Dict[str, Dict[str, Any]] = {}

def get_engine():
    if config.ENGINE == "cloudcode":
        return cloudcode_engine
    return cli_engine

def verify_token(credentials: Optional[HTTPAuthorizationCredentials] = Security(security)):
    """Validates the incoming API key from OpenCode."""
    if not config.REQUIRE_API_KEY:
        return True
    
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    incoming_key = credentials.credentials
    if incoming_key != config.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key provided",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return True

@app.get("/")
@app.get("/health")
async def health_check():
    """Health check endpoint showing bridge and local Antigravity status."""
    import os
    agy_path = cli_engine.bin_path
    agy_exists = bool(agy_path) and os.path.exists(agy_path) and (os.access(agy_path, os.X_OK) if os.name != "nt" else True)

    return {
        "status": "healthy",
        "service": "OpenAGY Bridge",
        "mode": "local-antigravity",
        "active_engine": config.ENGINE,
        "local_antigravity_bin": agy_path,
        "local_antigravity_ready": agy_exists,
        "active_requests": len(ACTIVE_REQUESTS),
        "endpoints": {
            "models": "/v1/models",
            "chat_completions": "/v1/chat/completions",
            "debug_status": "/debug/status"
        }
    }

@app.get("/debug/status")
async def debug_status():
    """Returns real-time status of active and recent requests for diagnosis."""
    now = time.time()
    active = []
    for r in list(ACTIVE_REQUESTS.values()):
        item = dict(r)
        item["elapsed_seconds"] = round(now - item["start_time"], 2)
        active.append(item)
    return {
        "active_requests_count": len(active),
        "active_requests": active,
        "recent_history": list(REQUEST_HISTORY)
    }

@app.get("/v1/models")
async def list_models(authorized: bool = Security(verify_token)):
    """Returns OpenAI-compatible model list for OpenCode model picker."""
    return JSONResponse(content=get_openai_models_response())

@app.post("/v1/chat/completions")
async def chat_completions(request: Request, authorized: bool = Security(verify_token)):
    """Main OpenAI chat completions endpoint consumed by OpenCode."""
    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON request body: {e}")

    stream = body.get("stream", False)
    engine = get_engine()
    model = body.get("model", "unknown")
    tools = body.get("tools", [])

    req_id = f"req-{uuid.uuid4().hex[:8]}"
    req_info: Dict[str, Any] = {
        "id": req_id,
        "start_time": time.time(),
        "model": model,
        "stream": stream,
        "tools_count": len(tools),
        "status": "processing",
        "tokens_emitted": 0,
        "duration": 0.0,
        "error": None
    }
    ACTIVE_REQUESTS[req_id] = req_info

    logger.info(f"[{req_id}] Incoming completion request for model '{model}' (stream={stream}, tools={len(tools)})")

    if stream:
        async def tracked_stream():
            try:
                async for chunk in engine.generate_stream(body):
                    if not chunk.startswith(":"):
                        req_info["tokens_emitted"] += 1
                        if req_info["status"] == "processing":
                            req_info["status"] = "streaming"
                    yield chunk
                req_info["status"] = "completed"
            except Exception as e:
                req_info["status"] = "error"
                req_info["error"] = str(e)
                logger.error(f"[{req_id}] Streaming error: {e}")
                raise
            finally:
                req_info["duration"] = round(time.time() - req_info["start_time"], 2)
                ACTIVE_REQUESTS.pop(req_id, None)
                REQUEST_HISTORY.append(req_info)
                logger.info(f"[{req_id}] Request finished in {req_info['duration']}s (status={req_info['status']}, tokens={req_info['tokens_emitted']})")

        return StreamingResponse(
            tracked_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Content-Type": "text/event-stream",
                "X-Accel-Buffering": "no"
            }
        )
    else:
        try:
            resp = await engine.generate(body)
            req_info["status"] = "completed"
            return JSONResponse(content=resp)
        except Exception as e:
            req_info["status"] = "error"
            req_info["error"] = str(e)
            logger.error(f"[{req_id}] Non-streaming error: {e}")
            raise
        finally:
            req_info["duration"] = round(time.time() - req_info["start_time"], 2)
            ACTIVE_REQUESTS.pop(req_id, None)
            REQUEST_HISTORY.append(req_info)
            logger.info(f"[{req_id}] Request finished in {req_info['duration']}s (status={req_info['status']})")
