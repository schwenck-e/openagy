import argparse
import logging
import os
import sys
from openagy.config import config

def main():
    parser = argparse.ArgumentParser(description="OpenAGY: OpenAI-Compatible Bridge for Antigravity (agy)")
    parser.add_argument("--host", type=str, default=config.HOST, help=f"Host to bind (default: {config.HOST})")
    parser.add_argument("--port", type=int, default=config.PORT, help=f"Port to bind (default: {config.PORT})")
    parser.add_argument("--engine", type=str, choices=["cli"], default="cli",
                        help="Backend engine: 'cli' (delegates strictly to local Antigravity binary 'agy')")
    parser.add_argument("--api-key", type=str, default=config.API_KEY, help="API Key required for requests")
    parser.add_argument("--require-key", action="store_true", default=config.REQUIRE_API_KEY,
                        help="Enforce API Key validation")
    parser.add_argument("--reload", dest="reload", action="store_true", help="Enable auto-reload on file changes")
    parser.add_argument("--no-reload", dest="reload", action="store_false", help="Disable auto-reload")
    default_reload = os.getenv("OPENAGY_RELOAD", "true").lower() in ("true", "1", "yes")
    parser.set_defaults(reload=default_reload)

    args = parser.parse_args()

    config.HOST = args.host
    config.PORT = args.port
    config.ENGINE = args.engine
    config.API_KEY = args.api_key
    config.REQUIRE_API_KEY = args.require_key

    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    print("=" * 60)
    print(" 🚀 Starting OpenAGY Bridge")
    print(f" -> Listening at: http://{config.HOST}:{config.PORT}")
    print(f" -> Models URL:   http://{config.HOST}:{config.PORT}/v1/models")
    print(f" -> Chat URL:     http://{config.HOST}:{config.PORT}/v1/chat/completions")
    print(f" -> Active Engine: {config.ENGINE}")
    print(f" -> API Key Auth: {'Required' if config.REQUIRE_API_KEY else 'Permissive (Accepts any key)'}")
    print("=" * 60)

    try:
        import uvicorn
        uvicorn.run("openagy.server:app", host=config.HOST, port=config.PORT, reload=args.reload)
    except ImportError:
        print("[!] Uvicorn not installed. Please install requirements with:")
        print("    pip install -r requirements.txt")
        sys.exit(1)

if __name__ == "__main__":
    main()
