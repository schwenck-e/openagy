import json
import logging
from typing import Optional
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
        "endpoints": {
            "models": "/v1/models",
            "chat_completions": "/v1/chat/completions"
        }
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

    logger.info(f"Incoming completion request for model '{body.get('model')}' (stream={stream})")

    if stream:
        return StreamingResponse(
            engine.generate_stream(body),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Content-Type": "text/event-stream",
                "X-Accel-Buffering": "no"
            }
        )
    else:
        resp = await engine.generate(body)
        return JSONResponse(content=resp)
