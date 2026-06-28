"""Store a generated four-hour digest JSON document in Redis.

The latest key is replaced only after a versioned key write succeeds. After the
new latest value is committed, the previous version key is deleted.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse, unquote

DEFAULT_TTL_SECONDS = 15_000
DEFAULT_LATEST_KEY = "news:digest:four-hour:latest"
DEFAULT_CURRENT_KEY = "news:digest:four-hour:current-key"
DEFAULT_PREFIX = "news:digest:four-hour:"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-file", default="-", help="JSON file path, or '-' for stdin")
    parser.add_argument("--redis-url", default=os.getenv("FOUR_HOUR_DIGEST_REDIS_URL") or os.getenv("REDIS_URL") or "")
    parser.add_argument("--latest-key", default=os.getenv("FOUR_HOUR_DIGEST_LATEST_KEY", DEFAULT_LATEST_KEY))
    parser.add_argument("--current-key", default=os.getenv("FOUR_HOUR_DIGEST_CURRENT_KEY", DEFAULT_CURRENT_KEY))
    parser.add_argument("--key-prefix", default=os.getenv("FOUR_HOUR_DIGEST_KEY_PREFIX", DEFAULT_PREFIX))
    parser.add_argument("--ttl-seconds", type=int, default=int(os.getenv("FOUR_HOUR_DIGEST_TTL_SECONDS", str(DEFAULT_TTL_SECONDS))))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    payload = load_payload(args.input_file)
    digest = validate_digest(payload)
    summary_id = str(digest.get("summaryId") or digest.get("generatedAt") or "latest")
    version_key = args.key_prefix.rstrip(":") + ":" + safe_key_fragment(summary_id)
    ttl = max(60, int(args.ttl_seconds))

    if args.dry_run:
        print(f"dry_run=true latest={args.latest_key} version={version_key} ttl={ttl}")
        return 0

    config = redis_config(args.redis_url)
    client = RedisRespClient(config)
    try:
        client.connect()
        old_key = decode_bulk(client.execute("GET", args.current_key))
        client.execute("MULTI")
        client.execute("SET", version_key, payload, "EX", str(ttl))
        client.execute("SET", args.latest_key, payload, "EX", str(ttl))
        client.execute("SET", args.current_key, version_key, "EX", str(ttl))
        client.execute("EXEC")
        if old_key and old_key != version_key:
            client.execute("DEL", old_key)
    finally:
        client.close()

    print(f"stored latest={args.latest_key} version={version_key} ttl={ttl}")
    return 0


def load_payload(input_file: str) -> str:
    if input_file == "-":
        payload = sys.stdin.read()
    else:
        payload = Path(input_file).read_text(encoding="utf-8-sig")
    return json.dumps(json.loads(payload), ensure_ascii=False, separators=(",", ":"))


def validate_digest(payload: str) -> dict:
    if "\ufffd" in payload:
        raise ValueError("digest contains replacement characters")
    if re.search(r"\?{3,}", payload):
        raise ValueError("digest contains repeated question-mark blocks")
    digest = json.loads(payload)
    if not isinstance(digest, dict):
        raise ValueError("digest must be a JSON object")
    for field in ("windowStart", "windowEnd", "generatedAt", "sections"):
        if field not in digest:
            raise ValueError(f"missing required digest field: {field}")
    return digest


def safe_key_fragment(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.:+-]+", "-", value.strip())
    return cleaned.strip("-") or "latest"


def decode_bulk(value):
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


@dataclass(frozen=True)
class RedisConfig:
    host: str
    port: int
    db: int
    password: str | None
    timeout_seconds: float


def redis_config(url: str) -> RedisConfig:
    if not url:
        host = os.getenv("FOUR_HOUR_DIGEST_REDIS_HOST") or os.getenv("SPRING_DATA_REDIS_HOST") or "127.0.0.1"
        port = int(os.getenv("FOUR_HOUR_DIGEST_REDIS_PORT") or os.getenv("SPRING_DATA_REDIS_PORT") or "6379")
        db = int(os.getenv("FOUR_HOUR_DIGEST_REDIS_DB", "0"))
        password = os.getenv("FOUR_HOUR_DIGEST_REDIS_PASSWORD") or None
        timeout = float(os.getenv("FOUR_HOUR_DIGEST_REDIS_TIMEOUT_SECONDS", "3"))
        return RedisConfig(host=host, port=port, db=db, password=password, timeout_seconds=timeout)

    parsed = urlparse(url)
    db_text = parsed.path.strip("/") or "0"
    return RedisConfig(
        host=parsed.hostname or "127.0.0.1",
        port=parsed.port or 6379,
        db=int(db_text),
        password=unquote(parsed.password) if parsed.password else None,
        timeout_seconds=float(os.getenv("FOUR_HOUR_DIGEST_REDIS_TIMEOUT_SECONDS", "3")),
    )


class RedisRespClient:
    def __init__(self, config: RedisConfig) -> None:
        self._config = config
        self._sock: socket.socket | None = None
        self._file = None

    def connect(self) -> None:
        self._sock = socket.create_connection(
            (self._config.host, self._config.port),
            timeout=self._config.timeout_seconds,
        )
        self._sock.settimeout(self._config.timeout_seconds)
        self._file = self._sock.makefile("rb")
        if self._config.password:
            self.execute("AUTH", self._config.password)
        if self._config.db:
            self.execute("SELECT", str(self._config.db))

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def execute(self, *args: str):
        if self._sock is None or self._file is None:
            raise RuntimeError("Redis client is not connected")
        encoded = self._encode(args)
        self._sock.sendall(encoded)
        return self._read_response()

    @staticmethod
    def _encode(args: tuple[str, ...]) -> bytes:
        chunks = [f"*{len(args)}\r\n".encode("ascii")]
        for arg in args:
            data = arg.encode("utf-8")
            chunks.append(f"${len(data)}\r\n".encode("ascii"))
            chunks.append(data + b"\r\n")
        return b"".join(chunks)

    def _read_response(self):
        line = self._file.readline()
        if not line:
            raise RuntimeError("Redis connection closed")
        prefix = line[:1]
        payload = line[1:-2]
        if prefix == b"+":
            return payload.decode("utf-8")
        if prefix == b"-":
            raise RuntimeError(payload.decode("utf-8", errors="replace"))
        if prefix == b":":
            return int(payload)
        if prefix == b"$":
            length = int(payload)
            if length < 0:
                return None
            data = self._file.read(length)
            self._file.read(2)
            return data
        if prefix == b"*":
            length = int(payload)
            if length < 0:
                return None
            return [self._read_response() for _ in range(length)]
        raise RuntimeError(f"unknown Redis response prefix: {prefix!r}")


if __name__ == "__main__":
    raise SystemExit(main())
