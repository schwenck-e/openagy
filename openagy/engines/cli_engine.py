import asyncio
import json
import logging
import os
import re
import shutil
import sys
import uuid
from typing import AsyncGenerator, Dict, Any, List, Optional, Tuple

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
    - Queue-buffered asynchronous subprocess streaming ensuring keep-alive pings
      never cancel or kill the underlying subprocess.
    - Robust, non-hanging pipe streaming on macOS, Linux, and Windows.
    - Concurrent stderr draining to eliminate OS pipe buffer deadlocks.
    - Zero-latency initial SSE role handshake chunk (< 5ms) to satisfy client response timers.
    - Native OpenAI Tool Calling / Function Calling support.
    - Conversation history preservation and Windows command-line length budgeting.
    """

    def __init__(self):
        self.bin_path = self._find_agy_bin()
        self._ensure_settings_permissions()

    def _find_agy_bin(self) -> str:
        is_windows = (os.name == "nt" or sys.platform == "win32")
        candidates = [
            config.AGY_BIN,
            shutil.which("agy.exe") if is_windows else None,
            shutil.which("agy"),
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
                # On Windows, if a .cmd or .bat was found, check if a native .exe is beside it to avoid cmd.exe length limits
                if is_windows and c.lower().endswith((".cmd", ".bat")):
                    base_no_ext = os.path.splitext(c)[0]
                    exe_sibling = base_no_ext + ".exe"
                    if os.path.exists(exe_sibling):
                        logger.info(f"Using native Windows executable instead of batch wrapper: {exe_sibling}")
                        return exe_sibling
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

    def _build_env(self) -> Dict[str, str]:
        """Prepares an execution environment ensuring PATH and UTF-8 encoding across macOS, Linux, and Windows."""
        env = os.environ.copy()
        extra_paths = [
            str(config.HOME / ".local" / "bin"),
            str(config.HOME / ".gemini" / "antigravity-cli" / "bin"),
            "/opt/homebrew/bin",
            "/usr/local/bin",
            "/usr/bin",
            "/bin"
        ]
        current_path = env.get("PATH", "")
        for p in extra_paths:
            if p not in current_path and os.path.exists(p):
                current_path = f"{p}:{current_path}"
        env["PATH"] = current_path
        env["PYTHONIOENCODING"] = "utf-8"
        return env

    def _get_max_prompt_length(self) -> int:
        """
        Determines the safe character budget for the prompt argument.
        Windows limits:
        - cmd.exe /c: 8,191 characters
        - CreateProcessW: 32,767 characters
        POSIX limits:
        - Linux/macOS ARG_MAX: 1-2 MB
        """
        is_windows = (os.name == "nt" or sys.platform == "win32")
        if is_windows:
            if self.bin_path.lower().endswith((".cmd", ".bat")):
                return 7200
            return 28000
        # Optimal budget for fast response times while preserving recent conversation turns
        return 48000

    def _extract_prompt(self, messages: list, tools: Optional[list] = None, max_length: int = 28000) -> str:
        """
        Formats OpenAI conversation history and tools into a structured prompt,
        strictly budgeted to fit within OS command line limits (preventing WinError 206).
        """
        system_instructions = []
        conversation_turns = []

        # 1. Inject tool definitions into system instructions if present (compact format)
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
                tools_json = json.dumps(formatted_tools, indent=None, ensure_ascii=False)
                tool_prompt = (
                    "You are operating as the language model engine for OpenCode.\n"
                    "CRITICAL: Do NOT execute local CLI tools, shell commands, or file edits yourself.\n"
                    "You only output completions. OpenCode has provided these workspace tools:\n"
                    f"{tools_json}\n\n"
                    "If you need to call a tool, you MUST output a tool call block in this exact JSON format:\n"
                    "```tool_call\n"
                    "{\"name\": \"<function_name>\", \"arguments\": { ... }}\n"
                    "```\n"
                    "If no tool is required, respond directly and concisely with normal text."
                )
                system_instructions.append(tool_prompt)
        else:
            system_instructions.append(
                "You are operating as the language model engine for OpenCode. "
                "Provide direct, high-quality answers, code solutions, and explanations without invoking background CLI commands or tools."
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
                tool_name = msg.get("name") or "tool"
                call_id = msg.get("tool_call_id") or ""
                id_info = f" (id: {call_id})" if call_id else ""
                tool_text = text_content.strip()
                # Cap excessive tool result outputs in history
                if len(tool_text) > 4000:
                    tool_text = tool_text[:2000] + "\n...[truncated]...\n" + tool_text[-1800:]
                conversation_turns.append(f"[Tool Execution Result for '{tool_name}'{id_info}]:\n{tool_text}")

        # 3. Assemble and budget prompt within max_length
        sys_str = ""
        if system_instructions:
            sys_str = "[System Instructions]\n" + "\n\n".join(system_instructions)

        overhead = len(sys_str) + 100
        available_history_budget = max(500, max_length - overhead)

        budgeted_turns = []
        current_len = 0
        for turn in reversed(conversation_turns):
            turn_len = len(turn) + 2
            if current_len + turn_len <= available_history_budget:
                budgeted_turns.insert(0, turn)
                current_len += turn_len
            else:
                if not budgeted_turns:
                    allowed = max(200, available_history_budget - 80)
                    truncated_turn = turn[:allowed] + "\n...[truncated to fit OS limit]..."
                    budgeted_turns.insert(0, truncated_turn)
                else:
                    budgeted_turns.insert(0, "[... earlier history omitted to fit OS command limit ...]")
                break

        prompt_parts = []
        if sys_str:
            prompt_parts.append(sys_str)
        else:
            prompt_parts.append(
                "[System Instruction]\n"
                "You are operating as the language model engine for OpenCode. "
                "Provide direct, high-quality answers, code solutions, and explanations without executing local terminal commands."
            )

        if len(budgeted_turns) == 1 and budgeted_turns[0].startswith("User: "):
            prompt_parts.append(budgeted_turns[0][6:])
        elif budgeted_turns:
            prompt_parts.append("[Conversation History]\n" + "\n\n".join(budgeted_turns))

        final_prompt = "\n\n".join(prompt_parts)
        if len(final_prompt) > max_length:
            final_prompt = final_prompt[:max_length - 60] + "\n...[truncated]..."

        return final_prompt

    def _parse_tool_call(self, text: str) -> Optional[Dict[str, Any]]:
        """Parses a tool call from a completed block or JSON response."""
        match = TOOL_CALL_REGEX.search(text)
        if match:
            raw_json = match.group(1).strip()
            try:
                data = json.loads(raw_json)
                if "name" in data:
                    return data
            except Exception:
                pass

        trimmed = text.strip()
        if trimmed.startswith("{") and trimmed.endswith("}"):
            try:
                data = json.loads(trimmed)
                if "name" in data and ("arguments" in data or "parameters" in data):
                    return data
            except Exception:
                pass

        return None

    async def _stream_subprocess_pipe(self, cmd: list[str]) -> AsyncGenerator[str, None]:
        """
        Universal high-throughput, low-latency streaming using standard asyncio
        subprocess pipes with an asynchronous queue and concurrent stderr draining.
        - Heartbeat safe: queue reads can time out without cancelling the subprocess.
        - Zero-hang EOF on macOS (no PTY kqueue bugs).
        - Zero-deadlock on Windows (continuously empties stderr buffer).
        """
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self._build_env()
        )

        queue: asyncio.Queue[Optional[str]] = asyncio.Queue()
        stderr_chunks: List[bytes] = []

        async def read_stdout():
            try:
                while True:
                    chunk = await proc.stdout.read(128)
                    if not chunk:
                        break
                    await queue.put(chunk.decode("utf-8", errors="replace"))
            except Exception as e:
                logger.debug(f"Stdout reader exception: {e}")
            finally:
                await queue.put(None)

        async def drain_stderr():
            try:
                while True:
                    err_chunk = await proc.stderr.read(1024)
                    if not err_chunk:
                        break
                    stderr_chunks.append(err_chunk)
            except Exception as e:
                logger.debug(f"Stderr drain exception: {e}")

        stdout_task = asyncio.create_task(read_stdout())
        stderr_task = asyncio.create_task(drain_stderr())

        try:
            while True:
                try:
                    # Heartbeat: if no token for 3s, yield SSE keep-alive without cancelling reader
                    chunk = await asyncio.wait_for(queue.get(), timeout=3.0)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue

                if chunk is None:
                    # EOF reached
                    break

                yield chunk

            # Await process exit and tasks cleanly without blocking indefinitely
            try:
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                if proc.returncode is None:
                    try:
                        proc.terminate()
                    except Exception:
                        pass
                await proc.wait()

            try:
                await asyncio.wait_for(stdout_task, timeout=2.0)
            except Exception:
                stdout_task.cancel()

            try:
                await asyncio.wait_for(stderr_task, timeout=2.0)
            except Exception:
                stderr_task.cancel()

            if proc.returncode != 0:
                err_text = b"".join(stderr_chunks).decode("utf-8", errors="replace").strip()
                if err_text:
                    logger.error(f"Antigravity process failed with code {proc.returncode}: {err_text}")
                    yield f"\n[Antigravity Process Error (exit code {proc.returncode}): {err_text}]"

        except asyncio.CancelledError:
            # Client aborted connection
            if proc.returncode is None:
                try:
                    proc.terminate()
                except Exception:
                    pass
            stdout_task.cancel()
            stderr_task.cancel()
            raise
        finally:
            if proc.returncode is None:
                try:
                    proc.terminate()
                except Exception:
                    pass
            if not stdout_task.done():
                stdout_task.cancel()
            if not stderr_task.done():
                stderr_task.cancel()

    async def generate_stream(
        self,
        openai_req: Dict[str, Any]
    ) -> AsyncGenerator[str, None]:
        requested_model = openai_req.get("model", "gemini-3.8-flash-high")
        resolved_model = resolve_model_name(requested_model)
        tools = openai_req.get("tools", [])
        chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"

        # 1. Immediately emit initial role handshake chunk (< 5ms)
        # This sends HTTP 200 headers and initial SSE frame instantly to OpenCode / AI SDK,
        # satisfying the client's initial response timeout immediately.
        yield OpenAIAdapter.create_chat_completion_chunk(
            chunk_id, requested_model, role="assistant", content=""
        )

        max_prompt_len = self._get_max_prompt_length()
        prompt = self._extract_prompt(openai_req.get("messages", []), tools=tools, max_length=max_prompt_len)

        # Build command: all flags MUST precede '-p' for Go CLI flag parsing
        cmd = [self.bin_path, "--dangerously-skip-permissions"]
        if resolved_model:
            cmd.extend(["--model", resolved_model])
        cmd.extend(["-p", prompt])

        # On Windows, wrap .cmd and .bat binaries with cmd.exe /c if an exe was not resolved
        if (os.name == "nt" or sys.platform == "win32") and self.bin_path.lower().endswith((".cmd", ".bat")):
            cmd = ["cmd.exe", "/c"] + cmd

        logger.info(f"Delegating to local Antigravity CLI: {self.bin_path} (model: {resolved_model}, tools={len(tools)}, prompt_len={len(prompt)})")

        stream_gen = self._stream_subprocess_pipe(cmd)

        accumulated_output = []
        is_tool_mode = bool(tools)
        # Track whether we are inside a tool_call block to suppress raw JSON from the text stream
        inside_tool_block = False

        try:
            async for raw_chunk in stream_gen:
                if raw_chunk.startswith(":"):
                    yield raw_chunk
                    continue

                clean_chunk = strip_ansi(raw_chunk)
                if not clean_chunk:
                    continue

                accumulated_output.append(clean_chunk)

                if is_tool_mode:
                    full_so_far = "".join(accumulated_output)
                    # Once a tool_call block opens, suppress further raw output from the text stream.
                    # This avoids sending raw JSON to the user while still accumulating it for parsing.
                    if not inside_tool_block:
                        if "```tool_call" in full_so_far or "<tool_call>" in full_so_far:
                            inside_tool_block = True
                        else:
                            # Still within normal text — stream it so OpenCode sees activity
                            yield OpenAIAdapter.create_chat_completion_chunk(
                                chunk_id, requested_model, content=clean_chunk
                            )
                    # if inside_tool_block: accumulate silently — do not yield raw JSON chunks
                else:
                    yield OpenAIAdapter.create_chat_completion_chunk(
                        chunk_id, requested_model, content=clean_chunk
                    )

        except Exception as e:
            logger.error(f"Error executing local Antigravity CLI: {e}")
            yield OpenAIAdapter.create_chat_completion_chunk(
                chunk_id, requested_model, content=f"\n[OpenAGY Local CLI Error: {e}]"
            )

        # ── Post-process: check for quota/auth errors embedded in the accumulated output ──
        full_text = "".join(accumulated_output)

        # Detect RESOURCE_EXHAUSTED (quota 429) from agy exit code 3 error message
        if "RESOURCE_EXHAUSTED" in full_text or "Individual quota reached" in full_text or "exit code 3" in full_text:
            import re as _re
            reset_match = _re.search(r"Resets in ([\w]+)", full_text)
            reset_info = f" Resets in {reset_match.group(1)}." if reset_match else ""
            logger.warning(f"AGY quota exhausted (429) for model {resolved_model}.{reset_info}")
            error_msg = (
                f"\n\n⚠️ **Quota esgotada** para `{resolved_model}`."
                f"{reset_info} Troque o modelo ou aguarde o reset da cota."
            )
            yield OpenAIAdapter.create_chat_completion_chunk(
                chunk_id, requested_model, content=error_msg, finish_reason="stop"
            )
            yield "data: [DONE]\n\n"
            return

        # After process completes: if tools are defined, check if a tool was called
        if is_tool_mode:
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
                    chunk_id, requested_model, tool_calls=tool_calls_payload, finish_reason="tool_calls"
                )
                yield "data: [DONE]\n\n"
                return

        # End stream normally
        yield OpenAIAdapter.create_chat_completion_chunk(
            chunk_id, requested_model, finish_reason="stop"
        )
        yield "data: [DONE]\n\n"

    async def generate(self, openai_req: Dict[str, Any]) -> Dict[str, Any]:
        full_text = []
        tool_calls = []
        requested_model = openai_req.get("model", "gemini-3.8-flash-high")
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
            requested_model,
            content="".join(full_text),
            tool_calls=tool_calls if tool_calls else None
        )
