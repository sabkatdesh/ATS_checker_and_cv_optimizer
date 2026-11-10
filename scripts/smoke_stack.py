# /// script
# requires-python = ">=3.12"
# dependencies = ["psycopg[binary]>=3.2", "redis>=5.2", "httpx>=0.28", "python-dotenv>=1.0"]
# ///
"""Smoke-check the dev stack: Supabase Postgres, Supabase Auth API, Redis.

Usage:  uv run scripts/smoke_stack.py
Reads DB__DSN, AUTH__SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, REDIS__URL from .env.
Prints only status lines; never prints secrets.
"""

from __future__ import annotations

import os
import sys
import time

import httpx
import psycopg
import redis
from dotenv import load_dotenv

TIMEOUT_S = 10


def check_postgres(dsn: str) -> str:
    started = time.perf_counter()
    with psycopg.connect(dsn, connect_timeout=TIMEOUT_S) as conn:
        version = conn.execute("select current_setting('server_version')").fetchone()[0]
        has_vector = conn.execute(
            "select count(*) from pg_available_extensions where name = 'vector'"
        ).fetchone()[0]
    ms = int((time.perf_counter() - started) * 1000)
    return f"postgres {version}, pgvector available={bool(has_vector)}, {ms} ms"


def check_auth(url: str, key: str) -> str:
    resp = httpx.get(f"{url}/auth/v1/health", headers={"apikey": key}, timeout=TIMEOUT_S)
    resp.raise_for_status()
    return f"auth health HTTP {resp.status_code}"


def check_redis(url: str) -> str:
    client = redis.Redis.from_url(url, socket_timeout=TIMEOUT_S, socket_connect_timeout=TIMEOUT_S)
    started = time.perf_counter()
    pong = client.ping()
    ms = int((time.perf_counter() - started) * 1000)
    return f"redis ping={pong}, {ms} ms"


def main() -> int:
    load_dotenv()
    checks = {
        "postgres": (check_postgres, ["DB__DSN"]),
        "auth": (check_auth, ["AUTH__SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY"]),
        "redis": (check_redis, ["REDIS__URL"]),
    }
    failures = 0
    for name, (fn, keys) in checks.items():
        missing = [k for k in keys if not os.getenv(k)]
        if missing:
            print(f"[SKIP] {name}: missing env {', '.join(missing)}")
            failures += 1
            continue
        try:
            print(f"[ OK ] {name}: {fn(*(os.environ[k] for k in keys))}")
        except Exception as exc:  # report type only; messages may contain hosts/creds
            print(f"[FAIL] {name}: {type(exc).__name__}")
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
