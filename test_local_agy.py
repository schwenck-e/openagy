import asyncio
import json
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("test_local_agy")

async def test_local():
    from openagy.engines.cli_engine import CliEngine
    from openagy.config import config

    print("=" * 60)
    print(" 🚀 Teste de Conexão com o Antigravity Local (agy)")
    print("=" * 60)

    engine = CliEngine()
    print(f"[✓] Binário do Antigravity localizado: {engine.bin_path}")

    is_valid_bin = bool(engine.bin_path) and os.path.exists(engine.bin_path) and (os.access(engine.bin_path, os.X_OK) if os.name != "nt" else True)
    if not is_valid_bin:
        print(f"[✗] Erro: O binário '{engine.bin_path}' não foi encontrado ou não é executável!")
        sys.exit(1)

    print("\n--- Enviando prompt de teste para o Antigravity local ---")
    test_req = {
        "model": "gemini-3.8-flash-high",
        "messages": [
            {"role": "user", "content": "Responda apenas com a frase 'Conexão local OpenAGY OK!' sem nenhuma formatação adicional."}
        ]
    }

    print("Streaming da resposta:")
    received_text = []
    async for chunk in engine.generate_stream(test_req):
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
                        received_text.append(content)
                        sys.stdout.write(content)
                        sys.stdout.flush()
            except Exception:
                pass

    print("\n" + "=" * 60)
    full_output = "".join(received_text).strip()
    if full_output:
        print(" 🎉 Sucesso! O Antigravity local executou e respondeu perfeitamente.")
        print(f" Resposta recebida: {full_output}")
    else:
        print(" ⚠️ Nenhuma saída foi recebida do Antigravity local.")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_local())
