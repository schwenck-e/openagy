import asyncio
import json
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("test_upstream")

async def run_diagnostics():
    from openagy.config import config
    from openagy.auth import auth_manager
    from openagy.adapter import OpenAIAdapter

    print("=" * 60)
    print(" 🔍 OpenAGY Upstream Diagnostic Tool")
    print("=" * 60)

    # Step 1: Token verification
    try:
        token = auth_manager.get_access_token()
        print(f"[✓] OAuth Token found! Prefix: {token[:12]}... (length: {len(token)})")
    except Exception as e:
        print(f"[✗] Failed to obtain OAuth token: {e}")
        return

    # Step 2: Project ID discovery
    print("\n--- Project ID Discovery ---")
    local_proj = auth_manager.get_project_id()
    if local_proj:
        print(f"[✓] Project ID found in local credentials/env: {local_proj}")
    else:
        print("[i] Project ID not found in local files. Querying loadCodeAssist backend...")

    resolved_proj = await auth_manager.resolve_project_id(token)
    if resolved_proj:
        print(f"[✓] Resolved cloudaicompanionProject: {resolved_proj}")
    else:
        print("[!] No project ID resolved from loadCodeAssist (will test with and without project envelope)")

    # Step 3: Upstream endpoint testing
    import httpx
    urls = [
        ("Cloud Code PA (Production)", config.UPSTREAM_URL),
        ("Daily Cloud Code PA (Staging)", config.BACKUP_UPSTREAM_URL),
    ]

    sample_req = {
        "model": "gemini-3.8-flash-high",
        "messages": [{"role": "user", "content": "Respond with the word 'HELLO_OPENAGY' and nothing else."}]
    }

    variants = [
        ("Envelope with Project", OpenAIAdapter.openai_to_cloudcode_payload(sample_req, "gemini-3.8-flash-high", project_id=resolved_proj)),
        ("Envelope without Project", OpenAIAdapter.openai_to_cloudcode_payload(sample_req, "gemini-3.8-flash-high", project_id=None)),
        ("Flat Gemini Payload", OpenAIAdapter.openai_to_flat_payload(sample_req, "gemini-3.8-flash-high")),
    ]

    print("\n--- Testing Connectivity to Upstream Endpoints ---")
    async with httpx.AsyncClient(timeout=30.0) as client:
        success = False
        for label, url in urls:
            print(f"\nTarget: {label} ({url})")
            for var_name, payload in variants:
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "User-Agent": "Antigravity-CLI/2.0 (macOS; arm64)",
                    "Accept": "text/event-stream",
                }
                if resolved_proj and "Project" in var_name:
                    headers["x-goog-user-project"] = resolved_proj

                try:
                    req = client.build_request("POST", url, headers=headers, json=payload)
                    resp = await client.send(req, stream=True)
                    if resp.status_code == 200:
                        print(f"  [✓] {var_name}: HTTP 200 OK (SUCCESS!)")
                        # Read first chunk
                        async for line in resp.aiter_lines():
                            if line.startswith("data: "):
                                print(f"      First Chunk: {line[:120]}...")
                                break
                        await resp.aclose()
                        success = True
                        break
                    else:
                        err_bytes = await resp.aread()
                        err_text = err_bytes.decode("utf-8", errors="replace").strip()
                        print(f"  [✗] {var_name}: HTTP {resp.status_code} - {err_text[:200]}")
                except Exception as ex:
                    print(f"  [✗] {var_name}: Connection exception: {ex}")

            if success:
                break

    print("\n" + "=" * 60)
    if success:
        print(" 🎉 Diagnostic successful! Upstream Google API is responding properly.")
    else:
        print(" ⚠️ Upstream Google API returned errors on all tested variants.")
        print(" Inspect the error details above to see the exact message returned by Google.")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(run_diagnostics())
