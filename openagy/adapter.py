import json
import time
import uuid
from typing import Dict, Any, List, Tuple, Optional

class OpenAIAdapter:
    """
    Translates between the OpenAI API protocol (used by OpenCode) and
    the Google Cloud Code Assist / Antigravity protocol.
    """

    THOUGHT_SIGNATURE_CACHE: Dict[str, str] = {}
    LAST_THOUGHT_SIGNATURE: Optional[str] = None

    @classmethod
    def record_thought_signature(cls, call_id: str, signature: str):
        """Caches thought signatures required for Gemini multi-turn tool calling."""
        if signature:
            if call_id:
                cls.THOUGHT_SIGNATURE_CACHE[call_id] = signature
            cls.LAST_THOUGHT_SIGNATURE = signature

    @classmethod
    def get_thought_signature(cls, call_id: str) -> Optional[str]:
        return cls.THOUGHT_SIGNATURE_CACHE.get(call_id) or cls.LAST_THOUGHT_SIGNATURE

    @classmethod
    def openai_to_cloudcode_payload(cls, openai_req: Dict[str, Any], resolved_model: str, project_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Converts OpenAI Chat Completion request parameters to the
        Cloud Code Assist GenerateContent payload.
        """
        messages = openai_req.get("messages", [])
        system_instruction_parts = []
        raw_contents = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            # System prompt handling
            if role == "system":
                if isinstance(content, str) and content:
                    system_instruction_parts.append({"text": content})
                elif isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            system_instruction_parts.append({"text": item.get("text", "")})
                continue

            # Assistant (model) message
            if role == "assistant":
                parts = []
                if content:
                    parts.append({"text": content if isinstance(content, str) else str(content)})
                
                # Check for tool_calls in assistant response
                tool_calls = msg.get("tool_calls", [])
                for tc in tool_calls:
                    func = tc.get("function", {})
                    fn_name = func.get("name", "")
                    fn_args_raw = func.get("arguments", "{}")
                    call_id = tc.get("id") or f"call_{uuid.uuid4().hex[:8]}"
                    try:
                        fn_args = json.loads(fn_args_raw) if isinstance(fn_args_raw, str) else fn_args_raw
                    except Exception:
                        fn_args = {}
                    
                    fc_data = {
                        "name": fn_name,
                        "args": fn_args,
                        "id": call_id
                    }
                    part_dict: Dict[str, Any] = {"functionCall": fc_data}
                    
                    sig = cls.get_thought_signature(call_id)
                    if sig:
                        part_dict["thoughtSignature"] = sig

                    parts.append(part_dict)
                
                if parts:
                    raw_contents.append({"role": "model", "parts": parts})
                continue

            # Tool result message
            if role == "tool":
                # Convert OpenAI tool response to Gemini functionResponse
                tool_name = msg.get("name") or "tool"
                call_id = msg.get("tool_call_id") or ""
                tool_content = content if isinstance(content, str) else json.dumps(content)
                f_resp: Dict[str, Any] = {
                    "name": tool_name,
                    "response": {"output": tool_content}
                }
                if call_id:
                    f_resp["id"] = call_id

                raw_contents.append({
                    "role": "user",
                    "parts": [{
                        "functionResponse": f_resp
                    }]
                })
                continue

            # User message
            parts = []
            if isinstance(content, str):
                if content:
                    parts.append({"text": content})
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            t = item.get("text", "")
                            if t:
                                parts.append({"text": t})
                        elif item.get("type") == "image_url":
                            # Support multimodal images if provided
                            img_url = item.get("image_url", {}).get("url", "")
                            if img_url.startswith("data:image/"):
                                # Parse base64
                                try:
                                    mime, b64_data = img_url.split(";base64,")
                                    mime_type = mime.replace("data:", "")
                                    parts.append({
                                        "inlineData": {
                                            "mimeType": mime_type,
                                            "data": b64_data
                                        }
                                    })
                                except Exception:
                                    pass
            if parts:
                raw_contents.append({"role": "user", "parts": parts})

        # Merge consecutive turns of the same role (required by Gemini protocol)
        merged_contents = []
        for c in raw_contents:
            if not c.get("parts"):
                continue
            if merged_contents and merged_contents[-1]["role"] == c["role"]:
                merged_contents[-1]["parts"].extend(c["parts"])
            else:
                merged_contents.append(c)

        # Generation config
        generation_config: Dict[str, Any] = {}
        if "temperature" in openai_req:
            generation_config["temperature"] = float(openai_req["temperature"])
        if "top_p" in openai_req:
            generation_config["topP"] = float(openai_req["top_p"])
        if "max_tokens" in openai_req:
            generation_config["maxOutputTokens"] = int(openai_req["max_tokens"])

        inner_request: Dict[str, Any] = {
            "contents": merged_contents,
        }

        if system_instruction_parts:
            inner_request["systemInstruction"] = {
                "parts": system_instruction_parts
            }

        if generation_config:
            inner_request["generationConfig"] = generation_config

        # Tools conversion (OpenAI functions -> Gemini functionDeclarations)
        tools = openai_req.get("tools", [])
        if tools:
            func_decls = []
            for tool in tools:
                if tool.get("type") == "function":
                    fn = tool.get("function", {})
                    func_decls.append({
                        "name": fn.get("name"),
                        "description": fn.get("description", ""),
                        "parameters": fn.get("parameters", {})
                    })
            if func_decls:
                inner_request["tools"] = [{"functionDeclarations": func_decls}]

        # Cloud Code PA expects envelope with 'model', optional 'project', and 'request'
        payload: Dict[str, Any] = {
            "model": resolved_model,
            "request": inner_request,
        }

        # Consumer projects (aicode-consumers, default-*) must not be passed in the project envelope
        if project_id and project_id != "aicode-consumers" and not project_id.startswith("default-"):
            payload["project"] = project_id

        return payload

    @staticmethod
    def openai_to_flat_payload(openai_req: Dict[str, Any], resolved_model: str) -> Dict[str, Any]:
        """Direct Gemini payload format without 'request' envelope (as fallback)."""
        envelope = OpenAIAdapter.openai_to_cloudcode_payload(openai_req, resolved_model)
        inner = envelope.get("request", {})
        return {
            "model": resolved_model,
            **inner
        }

    @staticmethod
    def create_chat_completion_chunk(
        chunk_id: str,
        model: str,
        content: Optional[str] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        finish_reason: Optional[str] = None,
        role: Optional[str] = None
    ) -> str:
        """Formats an SSE chunk in OpenAI specification."""
        delta: Dict[str, Any] = {}
        if role is not None:
            delta["role"] = role
        if content is not None:
            delta["content"] = content
        if tool_calls is not None:
            delta["tool_calls"] = tool_calls

        chunk = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": delta,
                    "finish_reason": finish_reason
                }
            ]
        }
        return f"data: {json.dumps(chunk)}\n\n"

    @staticmethod
    def create_chat_completion_response(
        req_id: str,
        model: str,
        content: str,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0
    ) -> Dict[str, Any]:
        """Formats non-streaming response in OpenAI specification."""
        message: Dict[str, Any] = {
            "role": "assistant",
            "content": content or None
        }
        finish_reason = "stop"
        if tool_calls:
            message["tool_calls"] = tool_calls
            finish_reason = "tool_calls"

        return {
            "id": req_id,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": message,
                    "finish_reason": finish_reason
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens or (len(str(message)) // 4),
                "completion_tokens": completion_tokens or (len(content) // 4),
                "total_tokens": (prompt_tokens or (len(str(message)) // 4)) + (completion_tokens or (len(content) // 4))
            }
        }
