import json
import logging
import time
import uuid
from typing import AsyncGenerator, Dict, Any, Optional, Tuple
from openagy.config import config
from openagy.auth import auth_manager
from openagy.models import resolve_model_name
from openagy.adapter import OpenAIAdapter

logger = logging.getLogger("openagy.engine.cloudcode")

class CloudCodeEngine:
    """
    Engine that interacts directly with Google's Cloud Code Assist / Antigravity API
    using the authenticated OAuth session of the local Antigravity CLI.
    """

    def __init__(self):
        pass

    async def generate_stream(
        self,
        openai_req: Dict[str, Any]
    ) -> AsyncGenerator[str, None]:
        """
        Streams completions from Cloud Code Assist backend and yields
        OpenAI-compatible Server-Sent Events (SSE).
        """
        import httpx

        requested_model = openai_req.get("model", "gemini-3.8-flash-high")
        resolved_model = resolve_model_name(requested_model)
        chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"

        token = auth_manager.get_access_token()
        project_id = await auth_manager.resolve_project_id(token)

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "Antigravity-CLI/2.0 (macOS; arm64)",
            "Accept": "text/event-stream",
        }
        if project_id:
            headers["x-goog-user-project"] = project_id

        # Prepare payload variants to ensure compatibility with Cloud Code PA
        payload_variants = []
        # Variant 1: Full envelope with project_id
        payload_variants.append(
            ("envelope_with_project", OpenAIAdapter.openai_to_cloudcode_payload(openai_req, resolved_model, project_id=project_id))
        )
        # Variant 2: Envelope without project_id (if project_id was present)
        if project_id:
            payload_variants.append(
                ("envelope_without_project", OpenAIAdapter.openai_to_cloudcode_payload(openai_req, resolved_model, project_id=None))
            )
        # Variant 3: Flat Gemini format (fallback)
        payload_variants.append(
            ("flat_gemini", OpenAIAdapter.openai_to_flat_payload(openai_req, resolved_model))
        )

        urls_to_try = [config.UPSTREAM_URL, config.BACKUP_UPSTREAM_URL]

        async with httpx.AsyncClient(timeout=120.0) as client:
            last_error = None
            response_stream = None

            for url in urls_to_try:
                for variant_name, payload in payload_variants:
                    try:
                        logger.debug(f"Attempting upstream {url} with variant '{variant_name}'...")
                        req = client.build_request("POST", url, headers=headers, json=payload)
                        resp = await client.send(req, stream=True)
                        if resp.status_code == 401:
                            logger.warning("Token expired (401), refreshing and retrying...")
                            token = auth_manager.get_access_token(force_refresh=True)
                            headers["Authorization"] = f"Bearer {token}"
                            req = client.build_request("POST", url, headers=headers, json=payload)
                            resp = await client.send(req, stream=True)

                        if resp.status_code == 200:
                            response_stream = resp
                            break
                        else:
                            error_bytes = await resp.aread()
                            err_text = error_bytes.decode("utf-8", errors="replace").strip()
                            logger.warning(
                                f"Endpoint {url} with variant '{variant_name}' returned status {resp.status_code}: {err_text[:300]}"
                            )
                            last_error = f"Status {resp.status_code} ({err_text})"
                    except Exception as e:
                        logger.warning(f"Connection failed for {url} with variant '{variant_name}': {e}")
                        last_error = str(e)
                
                if response_stream:
                    break

            if not response_stream:
                err_msg = f"Failed to connect to Antigravity upstream: {last_error}"
                yield OpenAIAdapter.create_chat_completion_chunk(
                    chunk_id, resolved_model, content=f"\n\n[OpenAGY Error: {err_msg}]"
                )
                yield OpenAIAdapter.create_chat_completion_chunk(
                    chunk_id, resolved_model, finish_reason="stop"
                )
                yield "data: [DONE]\n\n"
                return

            try:
                async for line in response_stream.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("data: "):
                        raw_data = line[6:].strip()
                        if raw_data == "[DONE]":
                            break
                        try:
                            cc_chunk = json.loads(raw_data)
                            candidates = cc_chunk.get("candidates") or cc_chunk.get("response", {}).get("candidates", [])
                            if not candidates:
                                continue
                            
                            cand = candidates[0]
                            content_obj = cand.get("content", {})
                            parts = content_obj.get("parts", [])
                            
                            for part in parts:
                                # Normal text response
                                if "text" in part and part["text"]:
                                    yield OpenAIAdapter.create_chat_completion_chunk(
                                        chunk_id, resolved_model, content=part["text"]
                                    )
                                # Tool / function call response
                                elif "functionCall" in part:
                                    fc = part["functionCall"]
                                    tc_data = [{
                                        "index": 0,
                                        "id": f"call_{uuid.uuid4().hex[:8]}",
                                        "type": "function",
                                        "function": {
                                            "name": fc.get("name", ""),
                                            "arguments": json.dumps(fc.get("args", {}))
                                        }
                                    }]
                                    yield OpenAIAdapter.create_chat_completion_chunk(
                                        chunk_id, resolved_model, tool_calls=tc_data
                                    )

                        except json.JSONDecodeError:
                            continue
            finally:
                await response_stream.aclose()

            # End stream
            yield OpenAIAdapter.create_chat_completion_chunk(
                chunk_id, resolved_model, finish_reason="stop"
            )
            yield "data: [DONE]\n\n"

    async def generate(self, openai_req: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handles non-streaming completion requests by collecting chunks.
        """
        full_text = []
        tool_calls = []
        model = resolve_model_name(openai_req.get("model", "gemini-3.8-flash-high"))
        req_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"

        async for chunk_str in self.generate_stream(openai_req):
            if chunk_str.startswith("data: "):
                data_part = chunk_str[6:].strip()
                if data_part == "[DONE]":
                    break
                try:
                    c = json.loads(data_part)
                    choices = c.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        if "content" in delta and delta["content"]:
                            full_text.append(delta["content"])
                        if "tool_calls" in delta and delta["tool_calls"]:
                            tool_calls.extend(delta["tool_calls"])
                except Exception:
                    pass

        return OpenAIAdapter.create_chat_completion_response(
            req_id,
            model,
            content="".join(full_text),
            tool_calls=tool_calls if tool_calls else None
        )
