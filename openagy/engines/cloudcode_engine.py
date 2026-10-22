import logging
from typing import AsyncGenerator, Dict, Any
from openagy.engines.cli_engine import CliEngine

logger = logging.getLogger("openagy.engine.cloudcode")

class CloudCodeEngine:
    """
    DEPRECATED & DISABLED: Direct HTTP calls to Google's backend API are strictly prohibited
    to prevent Google account bans and policy violations.
    All requests are routed directly to the local Antigravity binary ('agy').
    """
    def __init__(self):
        self._cli_engine = CliEngine()

    async def generate_stream(
        self,
        openai_req: Dict[str, Any]
    ) -> AsyncGenerator[str, None]:
        logger.warning(
            "CloudCodeEngine is disabled to enforce account safety. "
            "Delegating execution to local Antigravity binary ('agy')."
        )
        async for chunk in self._cli_engine.generate_stream(openai_req):
            yield chunk

    async def generate_completion(
        self,
        openai_req: Dict[str, Any]
    ) -> Dict[str, Any]:
        return await self._cli_engine.generate_completion(openai_req)
