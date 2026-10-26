import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
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
    r'(?:```(?:tool_call|json:tool_call|json)?\s*|<tool_call>)\s*(\{[\s\S]*?\})\s*(?:```|</tool_call>)',
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
    Guarantees 100% of network traffic, auth, and model calls are handled
    exclusively by the official local Antigravity binary on localhost.

    Now equipped with:
    - Native NDJSON streaming via '--output-format stream-json' for token-by-token fluid SSE.
    - Zero-latency initial SSE role handshake chunk (< 5ms) to satisfy client response timers.
    - Structured XML/JSON tool calling translated directly into standard OpenAI delta.tool_calls.
    - Disabled slash commands and skill scanning for fast turn execution.
    - Conversation history preservation and OS command-line budget management.
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
        Ensures ~/.gemini/antigravity-cli/settings.json exists with safe settings
        so headless print mode operates smoothly.
        """
        settings_path = config.HOME / ".gemini" / "antigravity-cli" / "settings.json"
        try:
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            if not settings_path.exists():
                with open(settings_path, "w", encoding="utf-8") as f:
                    json.dump({}, f)
        except Exception as e:
            logger.debug(f"Could not verify settings.json: {e}")

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
        # POSIX (macOS/Linux) supports ARG_MAX >= 1MB. Budget up to 200,000 characters
        # to ensure large tool schemas and full conversation history fit without truncation.
        return 200000

    def _extract_prompt(self, messages: list, tools: Optional[list] = None, max_length: int = 200000) -> str:
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
                    "You are operating as the AI language model for OpenCode.\n"
                    "CRITICAL RULES:\n"
                    "1. You are running as a pure completion engine. Do NOT execute local terminal commands, shell scripts, or file edits yourself.\n"
                    "2. OpenCode provides workspace tools that OpenCode executes:\n"
                    f"{tools_json}\n\n"
                    "3. If you need to call a tool, you MUST output a tool call block in this exact XML/JSON format:\n"
                    "<tool_call>\n"
                    "{\"name\": \"<function_name>\", \"arguments\": { ... }}\n"
                    "</tool_call>\n\n"
                    "4. If no tool is required, respond directly and concisely with standard markdown text."
                )
                system_instructions.append(tool_prompt)
        else:
            system_instructions.append(
                "You are operating as the AI language model for OpenCode. "
                "Provide direct, high-quality answers, code solutions, and explanations without invoking background terminal commands."
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
                        tc_blocks.append(f"<tool_call>\n{{\"name\": \"{fn_name}\", \"arguments\": {fn_args}}}\n</tool_call>")
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
                "You are operating as the AI language model for OpenCode. "
                "Provide direct, high-quality answers, code solutions, and explanations."
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
                if "tool_call" in data and isinstance(data["tool_call"], dict):
                    return data["tool_call"]
            except Exception:
                pass

        trimmed = text.strip()
        if "{" in trimmed and "}" in trimmed:
            sub = trimmed[trimmed.find("{"):trimmed.rfind("}") + 1]
            try:
                data = json.loads(sub)
                if "name" in data and ("arguments" in data or "parameters" in data):
                    return data
                if "tool_call" in data and isinstance(data["tool_call"], dict):
                    return data["tool_call"]
            except Exception:
                pass

        return None

    async def _stream_subprocess_asyncio(self, cmd: list[str]) -> AsyncGenerator[str, None]:
        """
        High-throughput, low-latency line streaming using asyncio subprocess pipes.
        Yields discrete NDJSON lines emitted by agy --output-format stream-json.
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
                    line_bytes = await proc.stdout.readline()
                    if not line_bytes:
                        break
                    line_str = line_bytes.decode("utf-8", errors="replace").strip()
                    if line_str:
                        await queue.put(line_str)
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
                    chunk = await asyncio.wait_for(queue.get(), timeout=3.0)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue

                if chunk is None:
                    break

                yield chunk

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
                    logger.warning(f"Antigravity CLI process ended with code {proc.returncode}: {err_text[:200]}")
                    yield json.dumps({"event": "result", "result": {"status": "ERROR", "error": err_text}})

        except asyncio.CancelledError:
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

    async def _stream_subprocess_popen(self, cmd: list[str]) -> AsyncGenerator[str, None]:
        """
        Thread-safe subprocess streaming fallback using subprocess.Popen.
        Operates reliably across all asyncio event loops on Windows (including SelectorEventLoop)
        without relying on loop-specific subprocess support.
        """
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[Optional[str]] = asyncio.Queue()
        stderr_chunks: List[bytes] = []

        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self._build_env()
        )

        def read_stdout():
            try:
                for line_bytes in iter(proc.stdout.readline, b""):
                    line_str = line_bytes.decode("utf-8", errors="replace").strip()
                    if line_str:
                        loop.call_soon_threadsafe(queue.put_nowait, line_str)
            except Exception as e:
                logger.debug(f"Stdout thread reader exception: {e}")
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        def drain_stderr():
            try:
                while True:
                    chunk = proc.stderr.read(1024)
                    if not chunk:
                        break
                    stderr_chunks.append(chunk)
            except Exception as e:
                logger.debug(f"Stderr thread drain exception: {e}")

        t_out = threading.Thread(target=read_stdout, daemon=True)
        t_err = threading.Thread(target=drain_stderr, daemon=True)
        t_out.start()
        t_err.start()

        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(queue.get(), timeout=3.0)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue

                if chunk is None:
                    break

                yield chunk

            try:
                await asyncio.to_thread(proc.wait)
            except Exception:
                pass

            t_out.join(timeout=1.0)
            t_err.join(timeout=1.0)

            if proc.returncode != 0:
                err_text = b"".join(stderr_chunks).decode("utf-8", errors="replace").strip()
                if err_text:
                    logger.warning(f"Antigravity CLI process ended with code {proc.returncode}: {err_text[:200]}")
                    yield json.dumps({"event": "result", "result": {"status": "ERROR", "error": err_text}})

        except asyncio.CancelledError:
            if proc.poll() is None:
                try:
                    proc.kill()
                except Exception:
                    pass
            raise
        finally:
            if proc.poll() is None:
                try:
                    proc.kill()
                except Exception:
                    pass

    async def _stream_subprocess_pipe(self, cmd: list[str]) -> AsyncGenerator[str, None]:
        """
        Universal high-throughput, low-latency line streaming.
        Attempts native asyncio subprocess execution first; seamlessly falls back to thread-safe
        subprocess.Popen streaming if the current event loop lacks subprocess support (e.g. Windows SelectorEventLoop).
        """
        try:
            async for chunk in self._stream_subprocess_asyncio(cmd):
                yield chunk
        except NotImplementedError:
            logger.info("Current asyncio event loop lacks create_subprocess_exec; using thread-safe Popen streaming.")
            async for chunk in self._stream_subprocess_popen(cmd):
                yield chunk

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

        # Build command: use official agy binary with --output-format stream-json
        # and --disable-slash-commands for fast, pure token-level streaming
        cmd = [
            self.bin_path,
            "--dangerously-skip-permissions",
            "--disable-slash-commands",
            "--output-format", "stream-json"
        ]
        if resolved_model:
            cmd.extend(["--model", resolved_model])
        cmd.extend(["-p", prompt])

        # On Windows, wrap .cmd and .bat binaries with cmd.exe /c if an exe was not resolved
        if (os.name == "nt" or sys.platform == "win32") and self.bin_path.lower().endswith((".cmd", ".bat")):
            cmd = ["cmd.exe", "/c"] + cmd

        logger.info(f"Delegating to local Antigravity CLI (NDJSON Stream): {self.bin_path} (model: {resolved_model}, tools={len(tools)}, prompt_len={len(prompt)})")

        stream_gen = self._stream_subprocess_pipe(cmd)

        accumulated_text_parts: List[str] = []
        is_tool_mode = bool(tools)
        inside_tool_block = False

        try:
            async for raw_line in stream_gen:
                if raw_line.startswith(":"):
                    yield raw_line
                    continue

                # Parse NDJSON event line from agy
                try:
                    event_data = json.loads(raw_line)
                except Exception:
                    # Non-JSON line from stdout fallback
                    clean_text = strip_ansi(raw_line)
                    if clean_text:
                        accumulated_text_parts.append(clean_text)
                        if not inside_tool_block:
                            yield OpenAIAdapter.create_chat_completion_chunk(
                                chunk_id, requested_model, content=clean_text
                            )
                    continue

                if not isinstance(event_data, dict):
                    continue

                evt = event_data.get("event")

                # Handle incremental token updates
                if evt == "step_update":
                    su = event_data.get("step_update", {})
                    text_delta = su.get("text_delta")
                    if not text_delta:
                        continue

                    accumulated_text_parts.append(text_delta)
                    full_so_far = "".join(accumulated_text_parts)

                    if is_tool_mode:
                        if not inside_tool_block:
                            if "<tool_call>" in full_so_far or "```tool_call" in full_so_far or "```json:tool_call" in full_so_far:
                                inside_tool_block = True
                            else:
                                # Normal conversational text emitted before any tool call
                                yield OpenAIAdapter.create_chat_completion_chunk(
                                    chunk_id, requested_model, content=text_delta
                                )
                        else:
                            # Inside tool call block: accumulate silently to protect OpenCode chat UI from raw JSON
                            pass
                    else:
                        yield OpenAIAdapter.create_chat_completion_chunk(
                            chunk_id, requested_model, content=text_delta
                        )

                elif evt == "result":
                    res_obj = event_data.get("result", {})
                    if res_obj.get("status") == "ERROR":
                        err_text = res_obj.get("error", "")
                        if err_text:
                            accumulated_text_parts.append(err_text)
                        logger.warning(f"Antigravity CLI turn error: {err_text}")

        except Exception as e:
            logger.error(f"Error executing local Antigravity CLI: {e}", exc_info=True)
            err_msg = str(e) or repr(e) or type(e).__name__
            yield OpenAIAdapter.create_chat_completion_chunk(
                chunk_id, requested_model, content=f"\n[OpenAGY Local CLI Error: {err_msg}]"
            )

        full_text = "".join(accumulated_text_parts)

        # Detect quota exhaustion (429) from agy
        if "RESOURCE_EXHAUSTED" in full_text or "Individual quota reached" in full_text or "exit code 3" in full_text:
            import re as _re
            reset_match = _re.search(r"Resets in ([\w]+)", full_text)
            reset_info = f" Resets in {reset_match.group(1)}." if reset_match else ""
            logger.warning(f"AGY quota exhausted (429) for model {resolved_model}.{reset_info}")
            error_msg = (
                f"\n\n⚠️ **Quota esgotada** para `{resolved_model}`."
                f"{reset_info} Troque o modelo no OpenCode ou aguarde o reset da cota."
            )
            yield OpenAIAdapter.create_chat_completion_chunk(
                chunk_id, requested_model, content=error_msg, finish_reason="stop"
            )
            yield "data: [DONE]\n\n"
            return

        # Handle tool calling emission for OpenCode
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
        """Handles non-streaming completion requests by collecting chunks."""
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
