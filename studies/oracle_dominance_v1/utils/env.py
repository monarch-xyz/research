from __future__ import annotations

import os
from pathlib import Path

from studies.oracle_dominance_v1.config import DEFAULT_ORACLE_GIST_BASE_URL, REPO_ROOT


def load_local_env() -> None:
    candidates = (
        REPO_ROOT / ".env",
        REPO_ROOT / ".env.local",
        Path.cwd() / ".env",
        Path.cwd() / ".env.local",
    )
    for candidate in candidates:
        if not candidate.exists():
            continue
        for raw_line in candidate.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def env(name: str) -> str | None:
    value = os.getenv(name)
    return value.strip() if value else None


def monarch_api_url() -> str:
    for key in (
        "MONARCH_INDEXER_ENDPOINT",
        "MONARCH_API_ENDPOINT",
        "NEXT_PUBLIC_MONARCH_API_NEW",
        "MONARCH_API_URL",
        "MONARCH_GRAPHQL_API_URL",
    ):
        value = env(key)
        if value:
            return value
    raise RuntimeError("Monarch endpoint not configured. Set MONARCH_INDEXER_ENDPOINT or MONARCH_API_ENDPOINT locally.")


def monarch_api_key() -> str | None:
    for key in ("MONARCH_API_KEY", "NEXT_PUBLIC_MONARCH_API_KEY", "MONARCH_GRAPHQL_API_KEY"):
        value = env(key)
        if value:
            return value
    return None


def oracle_gist_base_url() -> str:
    for key in ("ORACLE_GIST_BASE_URL", "NEXT_PUBLIC_ORACLE_GIST_BASE_URL"):
        value = env(key)
        if value:
            return value.rstrip("/")
    return DEFAULT_ORACLE_GIST_BASE_URL
