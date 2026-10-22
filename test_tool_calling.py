import asyncio
import json
import logging
import time
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("test_tool_calling")

async def run_tests():
    from openagy.server import get_engine
    from openagy.config import config

    print("=" * 60)
    print(f" 🛠️ Teste de Tool Calling e Latência (Engine: {config.ENGINE})")
    print("=" * 60)

    engine = get_engine()

    # Teste 1: Medição de Latência (Time to First Token)
    print("\n[1/2] Testando Latência de Inicialização e Streaming:")
    start_time = time.time()
    first_token_time = None
    total_tokens = 0

    req_latency = {
        "model": "gemini-3.8-flash-low",
        "messages": [
            {"role": "user", "content": "Conte de 1 a 5."}
        ]
    }

    sys.stdout.write("Saída: ")
    async for chunk in engine.generate_stream(req_latency):
        if chunk.startswith("data: "):
            raw = chunk[6:].strip()
            if raw == "[DONE]":
                break
            try:
                data = json.loads(raw)
                choices = data.get("choices", [])
                if choices:
                    content = choices[0].get("delta", {}).get("content", "")
                    if content:
                        if first_token_time is None:
                            first_token_time = time.time() - start_time
                        total_tokens += len(content.split())
                        sys.stdout.write(content)
                        sys.stdout.flush()
            except Exception:
                pass

    total_time = time.time() - start_time
    print(f"\n-> Tempo até o primeiro token (TTFT): {first_token_time:.2f}s" if first_token_time else "\n-> Sem tokens recebidos.")
    print(f"-> Tempo total de geração: {total_time:.2f}s")

    # Teste 2: Chamada de Ferramenta (Tool Calling)
    print("\n[2/2] Testando Chamada de Ferramentas (Tool Calling):")
    req_tool = {
        "model": "gemini-3.8-flash-low",
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "read_workspace_file",
                    "description": "Lê o conteúdo de um arquivo do projeto a partir do caminho relativo.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Caminho do arquivo, ex: 'package.json' ou 'README.md'"
                            }
                        },
                        "required": ["file_path"]
                    }
                }
            }
        ],
        "messages": [
            {
                "role": "user",
                "content": "Por favor, chame a ferramenta read_workspace_file para o arquivo 'README.md'."
            }
        ]
    }

    tool_called = False
    async for chunk in engine.generate_stream(req_tool):
        if chunk.startswith("data: "):
            raw = chunk[6:].strip()
            if raw == "[DONE]":
                break
            try:
                data = json.loads(raw)
                choices = data.get("choices", [])
                if choices:
                    tc = choices[0].get("delta", {}).get("tool_calls")
                    if tc:
                        tool_called = True
                        print(f"  [✓] Tool Call Detectada com Sucesso!")
                        print(f"      Função: {tc[0]['function']['name']}")
                        print(f"      Argumentos: {tc[0]['function']['arguments']}")
            except Exception:
                pass

    print("\n" + "=" * 60)
    if tool_called:
        print(" 🎉 Sucesso! O modelo chamou a ferramenta no formato OpenAI exigido pelo OpenCode.")
    else:
        print(" ℹ️ O modelo respondeu em texto (ou a ferramenta não foi disparada).")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(run_tests())
