"""Quick connectivity test for LLM providers (OpenAI + Anthropic).

Usage:
    python scripts/test_llm_connectivity.py              # test both
    python scripts/test_llm_connectivity.py anthropic    # test only anthropic
    python scripts/test_llm_connectivity.py openai       # test only openai

Reads env from .env (if present) and decrypts DPAPI key files.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# Allow importing the existing DPAPI helper
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from event_relay.weekly_summary import _load_secret_from_dpapi_file  # type: ignore


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def _resolve_key(env_key_name: str, file_env_name: str, default_file: str) -> str | None:
    direct = (os.getenv(env_key_name) or "").strip()
    if direct:
        return direct
    key_file = (os.getenv(file_env_name) or default_file).strip()
    return _load_secret_from_dpapi_file(key_file)


def test_anthropic() -> bool:
    print("\n=== Anthropic ===")
    key = _resolve_key("ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY_FILE", ".secrets/anthropic_api_key.dpapi")
    if not key:
        print("  FAIL: no API key (checked ANTHROPIC_API_KEY and ANTHROPIC_API_KEY_FILE)")
        return False
    print(f"  key loaded: sk-ant-...{key[-6:]}  (len={len(key)})")

    api_base = (os.getenv("ANTHROPIC_API_BASE") or "https://api.anthropic.com").strip().rstrip("/")
    model = (os.getenv("ANTHROPIC_MODEL") or "claude-sonnet-4-6").strip()
    url = f"{api_base}/v1/messages"
    payload = {
        "model": model,
        "max_tokens": 64,
        "messages": [{"role": "user", "content": "Reply with exactly: PONG"}],
    }
    req = Request(url, method="POST", data=json.dumps(payload).encode("utf-8"))
    req.add_header("x-api-key", key)
    req.add_header("anthropic-version", "2023-06-01")
    req.add_header("content-type", "application/json")

    print(f"  POST {url}  model={model}")
    try:
        with urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else str(exc)
        print(f"  FAIL: HTTP {exc.code}")
        print(f"  body: {err_body[:500]}")
        return False
    except URLError as exc:
        print(f"  FAIL: URLError {exc}")
        return False

    parsed = json.loads(body)
    text = ""
    for block in parsed.get("content", []) or []:
        if isinstance(block, dict) and block.get("type") == "text":
            text = str(block.get("text") or "").strip()
            break
    usage = parsed.get("usage", {})
    print(f"  reply: {text!r}")
    print(f"  usage: input={usage.get('input_tokens')}  output={usage.get('output_tokens')}")
    print("  OK")
    return True


def test_openai() -> bool:
    print("\n=== OpenAI ===")
    key = _resolve_key("WEEKLY_SUMMARY_OPENAI_API_KEY", "WEEKLY_SUMMARY_OPENAI_API_KEY_FILE", ".secrets/openai_api_key.dpapi")
    if not key:
        key = _resolve_key("OPENAI_API_KEY", "OPENAI_API_KEY_FILE", ".secrets/openai_api_key.dpapi")
    if not key:
        print("  FAIL: no API key")
        return False
    print(f"  key loaded: sk-...{key[-6:]}  (len={len(key)})")

    api_base = (os.getenv("WEEKLY_SUMMARY_OPENAI_API_BASE") or "https://api.openai.com/v1").strip().rstrip("/")
    model = (os.getenv("WEEKLY_SUMMARY_MODEL") or "gpt-5").strip()
    url = f"{api_base}/responses"
    payload = {
        "model": model,
        "input": "Reply with exactly: PONG",
        "text": {"format": {"type": "text"}},
    }
    req = Request(url, method="POST", data=json.dumps(payload).encode("utf-8"))
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", "application/json")

    print(f"  POST {url}  model={model}")
    try:
        with urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else str(exc)
        print(f"  FAIL: HTTP {exc.code}")
        print(f"  body: {err_body[:500]}")
        return False
    except URLError as exc:
        print(f"  FAIL: URLError {exc}")
        return False

    parsed = json.loads(body)
    text = (parsed.get("output_text") or "").strip()
    if not text:
        for item in parsed.get("output", []) or []:
            for part in (item.get("content") or []) if isinstance(item, dict) else []:
                if isinstance(part, dict) and part.get("type") == "output_text":
                    text = str(part.get("text") or "").strip()
                    if text:
                        break
            if text:
                break
    usage = parsed.get("usage", {})
    print(f"  reply: {text!r}")
    print(f"  usage: input={usage.get('input_tokens')}  output={usage.get('output_tokens')}")
    print("  OK")
    return True


def main() -> int:
    _load_env_file(ROOT / ".env")
    target = (sys.argv[1].lower() if len(sys.argv) > 1 else "both").strip()

    results: dict[str, bool] = {}
    if target in ("anthropic", "both"):
        results["anthropic"] = test_anthropic()
    if target in ("openai", "both"):
        results["openai"] = test_openai()

    print("\n=== Summary ===")
    for name, ok in results.items():
        print(f"  {name}: {'PASS' if ok else 'FAIL'}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
