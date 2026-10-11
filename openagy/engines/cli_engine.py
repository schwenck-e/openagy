import asyncio
import json
import logging
import os
import re
import shutil
import sys
import uuid
from typing import AsyncGenerator, Dict, Any, List, Optional, Tuple

try:
    import pty
except ImportError:
    pty = None

from openagy.config import config
from openagy.models import resolve_model_name
from openagy.adapter import OpenAIAdapter

logger = logging.getLogger("openagy.engine.cli")

ANSI_ESCAPE_PATTERN = re.compile(
    r'\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])'
)

TOOL_CALL_REGEX = re.compile(
    r'(?:```(?:tool_call|json)?\s*|<tool_call>)\s*(\{[\s\S]*?\})\s*(?:```|</tool_call>)',
    re.MULTILINE
)

def strip_ansi(text: str) -> str:
    """Removes ANSI terminal escape sequences and controls from text."""
    clean = ANSI_ESCAPE_PATTERN.sub('', text)
    clean = clean.replace('\r\n', '\n').replace('\r', '')
    return clean

class CliEngine:
    """
    Primary Engine: Executes completions by delegating directly to the
    locally installed Antigravity CLI ('agy') on the user's system.
    This guarantees that the bridge does NOT connect to Google APIs directly;
    instead, all networking, authentication, and model execution are handled
    by the local Antigravity session.

    Now equipped with:
    - High-throughput low-latency PTY streaming on Unix and pipe streaming on Windows.
    - Native OpenAI Tool Calling / Function Calling support.
    - Conversation history preservation for multi-turn tool loops.
    """

    def __init__(self):
        self.bin_path = self._find_agy_bin()
        self._ensure_settings_permissions()

    def _find_agy_bin(self) -> str:
        is_windows = (os.name == "nt" or sys.platform == "win32")
        candidates = [
            config.AGY_BIN,
            shutil.which("agy"),
            shutil.which("agy.exe") if is_windows else None,
            shutil.which("agy.cmd") if is_windows else None,
            str(config.HOME / ".local" / "bin" / ("agy.exe" if is_windows else "agy")),
            str(config.HOME / ".gemini" / "antigravity-cli" / "bin" / ("agy.exe" if is_windows else "agy")),
            "/usr/local/bin/agy",
            "/usr/bin/agy",
            "/opt/homebrew/bin/agy",
        ]
        if is_windows:
            local_app_data = os.getenv("LOCALAPPDATA")
            if local_app_data:
                candidates.extend([
                    os.path.join(local_app_data, "Programs", "antigravity", "bin", "agy.exe"),
                    os.path.join(local_app_data, "antigravity-cli", "bin", "agy.exe"),
                    os.path.join(local_app_data, "Microsoft", "WinGet", "Links", "agy.exe"),
                ])

        for c in candidates:
            if c and os.path.exists(c):
                if not is_windows and not os.access(c, os.X_OK):
                    continue
                logger.info(f"Using local Antigravity binary at: {c}")
                return c
        logger.warning(f"Defaulting to configured AGY_BIN path: {config.AGY_BIN}")
        return config.AGY_BIN

    def _ensure_settings_permissions(self):
        """
        Ensures ~/.gemini/antigravity-cli/settings.json has permissions.allow configured
        so jetski in headless mode doesn't auto-deny tools.
        """
        settings_path = config.HOME / ".gemini" / "antigravity-cli" / "settings.json"
        try:
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            data = {}
            if settings_path.exists():
                with open(settings_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

            perms = data.get("permissions", {})
            allow_list = perms.get("allow", [])

            needed = ["command(*)", "command()", "read_file(*)", "edit_file(*)", "*"]
            changed = False
            for item in needed:
                if item not in allow_list:
                    allow_list.append(item)
                    changed = True

            if changed:
                perms["allow"] = allow_list
                data["permissions"] = perms
                with open(settings_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                logger.info(f"Updated permissions.allow in {settings_path}")
        except Exception as e:
            logger.debug(f"Could not update settings.json: {e}")

    def _extract_prompt(self, messages: list, tools: Optional[list] = None) -> str:
        """
        Formats OpenAI conversation history and tools into a structured prompt
        that allows the local model to understand context and execute tool calls.
        """
        system_instructions = []
        conversation_turns = []

        # 1. Inject tool definitions into system instructions if present
        if tools:
            formatted_tools = []
            for t in tools:
                if t.get("type") == "function":
                    fn = t.get("function", {})
                    formatted_tools.append({
                        "name": fn.get("name"),
                        "description": fn.get("description", ""),
                        "parameters": fn.get("parameters", {})
                    })

            if formatted_tools:
                tools_json = json.dumps(formatted_tools, indent=2, ensure_ascii=False)
                tool_prompt = (
                    "You are operating as the language model engine for OpenCode.\n"
                    "You have access to the following workspace tools:\n"
                    f"{tools_json}\n\n"
                    "If you need to call a tool, you MUST output a tool call block in this exact JSON format:\n"
                    "```tool_call\n"
                    "{\"name\": \"<function_name>\", \"arguments\": { ... }}\n"
                    "```\n"
                    "If no tool is required, respond directly with normal text."
                )
                system_instructions.append(tool_prompt)
        else:
            system_instructions.append(
                "You are operating as the language model engine for OpenCode. "
                "Provide direct, high-quality answers, code solutions, and explanations without invoking background CLI commands."
            )

        # 2. Process conversation history
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            # Format content if it's a list (multimodal or structured text blocks)
            text_content = ""
            if isinstance(content, str):
                text_content = content
            elif isinstance(content, list):
                parts = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        parts.append(item.get("text", ""))
                    elif isinstance(item, str):
                        parts.append(item)
                text_content = "\n".join(parts)
            else:
                text_content = str(content)

            if role == "system":
                if text_content.strip():
                    system_instructions.append(text_content.strip())

            elif role == "user":
                if text_content.strip():
                    conversation_turns.append(f"User: {text_content.strip()}")

            elif role == "assistant":
                tc_list = msg.get("tool_calls", [])
                if tc_list:
                    # Assistant previous tool invocations
                    tc_blocks = []
                    for tc in tc_list:
                        fn = tc.get("function", {})
                        fn_name = fn.get("name", "")
                        fn_args = fn.get("arguments", "{}")
                        tc_blocks.append(f"```tool_call\n{{\"name\": \"{fn_name}\", \"arguments\": {fn_args}}}\n```")
                    body = f"Assistant: {text_content}\n" + "\n".join(tc_blocks) if text_content else "Assistant:\n" + "\n".join(tc_blocks)
                    conversation_turns.append(body.strip())
                elif text_content.strip():
                    conversation_turns.append(f"Assistant: {text_content.strip()}")

            elif role == "tool":
                # Result of a tool execution sent back by OpenCode
                tool_name = msg.get("name") or "tool"
                call_id = msg.get("tool_call_id") or ""
                id_info = f" (id: {call_id})" if call_id else ""
                conversation_turns.append(f"[Tool Execution Result for '{tool_name}'{id_info}]:\n{text_content.strip()}")

        prompt_parts = []
        if system_instructions:
            prompt_parts.append("[System Instructions]\n" + "\n\n".join(system_instructions))

        if len(conversation_turns) == 1 and conversation_turns[0].startswith("User: "):
            # Single user turn, remove redundant prefix
            prompt_parts.append(conversation_turns[0][6:])
        elif conversation_turns:
            prompt_parts.append("[Conversation History]\n" + "\n\n".join(conversation_turns))

        return "\n\n".join(prompt_parts)

    def _parse_tool_call(self, text: str) -> Optional[Dict[str, Any]]:
        """Parses a tool call from a completed block or JSON response."""
        # 1. Check for ```tool_call ... ``` or <tool_call> ... </tool_call>
        match = TOOL_CALL_REGEX.search(text)
        if match:
            raw_json = match.group(1).strip()
            try:
                data = json.loads(raw_json)
                if "name" in data:
                    return data
            except Exception:
                pass

        # 2. Check if the entire string is a JSON object with name & arguments
        trimmed = text.strip()
        if trimmed.startswith("{") and trimmed.endswith("}"):
            try:
                data = json.loads(trimmed)
                if "name" in data and ("arguments" in data or "parameters" in data):
                    return data
            except Exception:
                pass

        return None

    async def _stream_subprocess_pty(self, cmd: list[str]) -> AsyncGenerator[str, None]:
        """
        Executes the command inside a pseudo-terminal (PTY) with small chunk reads
        (128 bytes) to achieve low-latency, immediate token streaming.
        """
        master_fd, slave_fd = pty.openpty()
        slave_closed = False
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=slave_fd,
                stderr=slave_fd,
                close_fds=True
            )
            os.close(slave_fd)
            slave_closed = True

            loop = asyncio.get_running_loop()
            reader = asyncio.StreamReader()
            protocol = asyncio.StreamReaderProtocol(reader)
            transport, _ = await loop.connect_read_pipe(
                lambda: protocol, os.fdopen(master_fd, 'rb', buffering=0)
            )

            try:
                while True:
                    # Small buffer read (128 bytes) for immediate, low-latency streaming
                    chunk = await reader.read(128)
                    if not chunk:
                        break
                    text = chunk.decode("utf-8", errors="replace")
                    yield text
            finally:
                transport.close()

            await proc.wait()
        finally:
            if not slave_closed:
                try:
                    os.close(slave_fd)
                except Exception:
                    pass

    async def _stream_subprocess_pipe(self, cmd: list[str]) -> AsyncGenerator[str, None]:
        """Fallback execution using standard asyncio subprocess pipes."""
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        while True:
            chunk = await proc.stdout.read(128)
            if not chunk:
                break
            yield chunk.decode("utf-8", errors="replace")

        await proc.wait()
        if proc.returncode != 0:
            err = await proc.stderr.read()
            if err:
                yield f"\n[Antigravity Process Error: {err.decode('utf-8', errors='replace')}]"

    async def generate_stream(
        self,
        openai_req: Dict[str, Any]
    ) -> AsyncGenerator[str, None]:
        requested_model = openai_req.get("model", "gemini-3.8-flash-high")
        resolved_model = resolve_model_name(requested_model)
        tools = openai_req.get("tools", [])
        chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"

        prompt = self._extract_prompt(openai_req.get("messages", []), tools=tools)

        # Build command: all flags MUST precede '-p' for Go CLI flag parsing
        cmd = [self.bin_path, "--dangerously-skip-permissions"]
        if resolved_model:
            cmd.extend(["--model", resolved_model])
        cmd.extend(["-p", prompt])

        # On Windows, wrap .cmd and .bat binaries with cmd.exe /c
        if (os.name == "nt" or sys.platform == "win32") and self.bin_path.lower().endswith((".cmd", ".bat")):
            cmd = ["cmd.exe", "/c"] + cmd

        logger.info(f"Delegating to local Antigravity CLI: {self.bin_path} (model: {resolved_model}, tools={len(tools)})")

        stream_gen = None
        if pty is None or os.name == "nt" or sys.platform == "win32":
            stream_gen = self._stream_subprocess_pipe(cmd)
        else:
            try:
                stream_gen = self._stream_subprocess_pty(cmd)
            except Exception as e:
                logger.debug(f"PTY initialization failed ({e}), falling back to standard pipe.")
                stream_gen = self._stream_subprocess_pipe(cmd)

        accumulated_output = []
        is_tool_mode = bool(tools)

        try:
            async for raw_chunk in stream_gen:
                clean_chunk = strip_ansi(raw_chunk)
                if not clean_chunk:
                    continue

                accumulated_output.append(clean_chunk)

                # If tools are enabled, check if a tool call tag is starting
                # If no tool tag in stream, stream chunk immediately to minimize latency
                full_so_far = "".join(accumulated_output)
                if not is_tool_mode or ("```tool_call" not in full_so_far and "<tool_call>" not in full_so_far):
                    yield OpenAIAdapter.create_chat_completion_chunk(
                        chunk_id, resolved_model, content=clean_chunk
                    )

        except Exception as e:
            logger.error(f"Error executing local Antigravity CLI: {e}")
            yield OpenAIAdapter.create_chat_completion_chunk(
                chunk_id, resolved_model, content=f"\n[OpenAGY Local CLI Error: {e}]"
            )

        # After process completes: if tools are defined, check if a tool was called
        if is_tool_mode:
            full_text = "".join(accumulated_output)
            tool_data = self._parse_tool_call(full_text)
            if tool_data:
                tool_name = tool_data.get("name", "")
                raw_args = tool_data.get("arguments", {})
                args_str = json.dumps(raw_args) if isinstance(raw_args, (dict, list)) else str(raw_args)

                tool_calls_payload = [{
                    "index": 0,
                    "id": f"call_{uuid.uuid4().hex[:8]}",
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": args_str
                    }
                }]
                logger.info(f"Tool call emitted by local Antigravity: {tool_name}")
                yield OpenAIAdapter.create_chat_completion_chunk(
                    chunk_id, resolved_model, tool_calls=tool_calls_payload, finish_reason="tool_calls"
                )
                yield "data: [DONE]\n\n"
                return

        # End stream normally
        yield OpenAIAdapter.create_chat_completion_chunk(
            chunk_id, resolved_model, finish_reason="stop"
        )
        yield "data: [DONE]\n\n"

    async def generate(self, openai_req: Dict[str, Any]) -> Dict[str, Any]:
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
