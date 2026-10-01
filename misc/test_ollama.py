"""
Quick smoke test for the Ollama container running via docker compose,
or for Ollama Cloud directly via --cloud.

Usage:
    python misc/test_ollama.py                       # default: llama3.2 via local container
    python misc/test_ollama.py llama3.1:8b           # any model name
    python misc/test_ollama.py --list                # list locally available models
    python misc/test_ollama.py --stream              # stream tokens
    python misc/test_ollama.py --chat                # use /api/chat
    python misc/test_ollama.py --cloud               # hit https://ollama.com directly
    python misc/test_ollama.py --cloud --model llama3.2
    python misc/test_ollama.py --api-key ollama_xxx  # override the env var
    python misc/test_ollama.py --pull                # pull default model via /api/pull
    python misc/test_ollama.py qwen2.5-coder:7b-cloud --cloud --pull   # pull + run a cloud model

The script needs no third-party packages — stdlib only.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

# Local container endpoint (the port published by the `ollama` service in docker-compose.yml)
LOCAL_URL = "http://localhost:11435"
# Ollama Cloud endpoint
CLOUD_URL = "https://ollama.com"
DEFAULT_MODEL = "llama3.2"


def _auth_headers(api_key: str | None) -> dict[str, str]:
    """Build request headers, including Authorization for Ollama Cloud."""
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def list_models(base_url: str, api_key: str | None = None) -> list[str]:
    """Fetch the locally available model list from Ollama."""
    req = urllib.request.Request(f"{base_url}/api/tags", method="GET")
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return [m["name"] for m in data.get("models", [])]


def pull_model(base_url: str, model: str, api_key: str | None = None) -> None:
    """POST /api/pull. Streams progress JSON to stderr; raises HTTPError on failure."""
    payload = {"name": model, "stream": True}
    req = urllib.request.Request(
        f"{base_url}/api/pull",
        data=json.dumps(payload).encode("utf-8"),
        headers=_auth_headers(api_key),
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=3600) as resp:
        last_pct = -1
        for line in resp:
            if not line.strip():
                continue
            chunk = json.loads(line.decode("utf-8"))
            status = chunk.get("status", "")
            completed = chunk.get("completed")
            total = chunk.get("total")
            if completed and total:
                pct = int(completed * 100 / total)
                # only reprint when the percentage moves, to keep stderr tidy
                if pct != last_pct:
                    print(
                        f"  {status} {pct}% ({completed // (1024 * 1024)}/"
                        f"{total // (1024 * 1024)} MiB)",
                        file=sys.stderr,
                    )
                    last_pct = pct
            elif status:
                print(f"  {status}", file=sys.stderr)
            if status == "success":
                return
        # If the stream ended without an explicit success, that's fine — Ollama
        # closed the connection cleanly. Surface a confirmation either way.
        print(f"  pull complete: {model}", file=sys.stderr)


def generate(
    base_url: str,
    model: str,
    prompt: str,
    stream: bool = False,
    api_key: str | None = None,
) -> None:
    """POST /api/generate. Streams chunks if stream=True, else prints one response."""
    payload = {"model": model, "prompt": prompt, "stream": stream}
    req = urllib.request.Request(
        f"{base_url}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers=_auth_headers(api_key),
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=300) as resp:
        if stream:
            # Ollama returns newline-delimited JSON chunks
            for line in resp:
                if not line.strip():
                    continue
                chunk = json.loads(line.decode("utf-8"))
                sys.stdout.write(chunk.get("response", ""))
                sys.stdout.flush()
                if chunk.get("done"):
                    break
            print()  # trailing newline
        else:
            data = json.loads(resp.read().decode("utf-8"))
            print(data.get("response", "").strip())


def chat(
    base_url: str,
    model: str,
    prompt: str,
    stream: bool = False,
    api_key: str | None = None,
) -> None:
    """POST /api/chat — same idea but with message roles, useful for n8n-style agents."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": stream,
    }
    req = urllib.request.Request(
        f"{base_url}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers=_auth_headers(api_key),
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=300) as resp:
        if stream:
            for line in resp:
                if not line.strip():
                    continue
                chunk = json.loads(line.decode("utf-8"))
                msg = chunk.get("message", {}).get("content", "")
                sys.stdout.write(msg)
                sys.stdout.flush()
                if chunk.get("done"):
                    break
            print()
        else:
            data = json.loads(resp.read().decode("utf-8"))
            print(data.get("message", {}).get("content", "").strip())


def main() -> int:
    parser = argparse.ArgumentParser(description="Test the Ollama container or Ollama Cloud.")
    parser.add_argument(
        "model",
        nargs="?",
        default=DEFAULT_MODEL,
        help=f"Model name to query (default: {DEFAULT_MODEL}).",
    )
    parser.add_argument(
        "--prompt",
        default="In one sentence, explain what an n8n workflow is.",
        help="Prompt to send to the model.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available models and exit.",
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        help="Stream the response token by token.",
    )
    parser.add_argument(
        "--chat",
        action="store_true",
        help="Use /api/chat instead of /api/generate.",
    )
    parser.add_argument(
        "--url",
        default=LOCAL_URL,
        help=f"Ollama base URL (default: {LOCAL_URL}). Use {CLOUD_URL} with --cloud.",
    )
    parser.add_argument(
        "--cloud",
        action="store_true",
        help=f"Hit Ollama Cloud at {CLOUD_URL} using OLLAMA_CLOUD_API_KEY from env.",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Override the API key (otherwise uses OLLAMA_CLOUD_API_KEY env var).",
    )
    parser.add_argument(
        "--pull",
        action="store_true",
        help="Pull the model via /api/pull first, then continue with the request.",
    )
    args = parser.parse_args()

    base_url = CLOUD_URL if args.cloud else args.url
    api_key = args.api_key or os.environ.get("OLLAMA_CLOUD_API_KEY")
    if args.cloud and not api_key:
        print("OLLAMA_CLOUD_API_KEY is not set in your environment.", file=sys.stderr)
        print("Set it (PowerShell): $env:OLLAMA_CLOUD_API_KEY='ollama_xxx'", file=sys.stderr)
        print("Or pass it inline: --api-key ollama_xxx", file=sys.stderr)
        return 1

    print(
        f"→ {base_url}  model={args.model}  stream={args.stream}  "
        f"chat={args.chat}  auth={'bearer' if api_key else 'none'}"
    )

    try:
        if args.pull:
            print(f"→ pulling {args.model} from {base_url}", file=sys.stderr)
            pull_model(base_url, args.model, api_key)
            if args.list:
                # Pull was the requested action — no need to re-list afterward.
                return 0

        if args.list:
            models = list_models(base_url, api_key)
            if not models:
                print("No models available (or cloud returned an empty list).")
                if not args.cloud:
                    print(
                        f"Hint: pull one with  docker exec -it ollama_ai ollama pull {args.model}"
                    )
            else:
                print("Available models:")
                for m in models:
                    print(f"  - {m}")
            return 0

        if args.chat:
            chat(base_url, args.model, args.prompt, args.stream, api_key)
        else:
            generate(base_url, args.model, args.prompt, args.stream, api_key)
        return 0

    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"\nHTTP {exc.code} from Ollama:\n{body}", file=sys.stderr)
        if exc.code == 404:
            print(f"\nModel '{args.model}' not found.", file=sys.stderr)
            if args.cloud:
                print(
                    "  Cloud models must be in the ollama.com catalog "
                    "(check https://ollama.com/library).",
                    file=sys.stderr,
                )
            else:
                print(
                    "  - Pull it:    docker exec -it ollama_ai ollama pull "
                    f"{args.model}",
                    file=sys.stderr,
                )
                print(
                    "  - Or cloud:   python misc/test_ollama.py "
                    f"{args.model} --cloud",
                    file=sys.stderr,
                )
        elif exc.code == 401:
            print(
                "\nUnauthorized. Check OLLAMA_CLOUD_API_KEY and that it's "
                "set in the current shell.",
                file=sys.stderr,
            )
        return exc.code

    except urllib.error.URLError as exc:
        print(f"\nCould not reach Ollama at {base_url}: {exc}", file=sys.stderr)
        print("Is the container running?  docker compose ps", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
