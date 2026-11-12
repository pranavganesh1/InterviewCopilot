"""Probe LiteLLM model groups used by the app (never prints keys or bodies).

Usage (from backend/):
  uv run python scripts/llm_check.py
  uv run python scripts/llm_check.py --structured

Do not run this in CI with production keys. It only prints status/cause/latency.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.gateway.llm import MODEL_FALLBACKS, LLMCause, classify_http_failure  # noqa: E402


def _model_groups(config_path: Path) -> list[str]:
    names: list[str] = []
    # Prefer names declared in the LiteLLM config (no YAML dependency).
    if config_path.is_file():
        text = config_path.read_text(encoding="utf-8")
        for match in re.finditer(r"^\s*-\s*model_name:\s*([^\s#]+)", text, re.M):
            name = match.group(1).strip().strip("\"'")
            if name and name not in names:
                names.append(name)
    for primary, fallbacks in MODEL_FALLBACKS.items():
        for name in (primary, *fallbacks):
            if name not in names:
                names.append(name)
    return names


def _provider_code(body: object) -> str | None:
    if not isinstance(body, dict):
        return None
    err = body.get("error")
    if isinstance(err, dict):
        for key in ("code", "type", "status"):
            val = err.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()[:80]
    return None


async def _probe(
    client: httpx.AsyncClient,
    *,
    base: str,
    key: str,
    model: str,
    structured: bool,
) -> tuple[int | None, str, float]:
    payload: dict = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": (
                    'Reply with JSON {"ok":true} only.'
                    if structured
                    else "Reply with the single word pong."
                ),
            }
        ],
        "max_tokens": 16,
    }
    if structured:
        payload["response_format"] = {"type": "json_object"}
    started = time.monotonic()
    try:
        resp = await client.post(
            f"{base.rstrip('/')}/v1/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {key}"},
            timeout=20.0,
        )
    except httpx.TimeoutException:
        return None, LLMCause.timeout.value, (time.monotonic() - started) * 1000
    except httpx.HTTPError:
        return None, LLMCause.network.value, (time.monotonic() - started) * 1000
    latency = (time.monotonic() - started) * 1000
    body = None
    try:
        body = resp.json()
    except Exception:
        body = None
    cause = classify_http_failure(
        resp.status_code if resp.status_code >= 400 else None,
        provider_code=_provider_code(body),
    )
    if resp.status_code < 400:
        return resp.status_code, "ok", latency
    return resp.status_code, cause.value, latency


async def main() -> int:
    parser = argparse.ArgumentParser(description="Probe LiteLLM model groups")
    parser.add_argument(
        "--structured",
        action="store_true",
        help="Also send a tiny JSON-mode request per group",
    )
    parser.add_argument(
        "--config",
        default=str(
            Path(__file__).resolve().parents[2] / "infra" / "litellm" / "config.yaml"
        ),
        help="Path to LiteLLM config.yaml (structure only; keys never printed)",
    )
    args = parser.parse_args()
    settings = get_settings()
    groups = _model_groups(Path(args.config))
    print(f"{'group':<28} {'status':>6} {'cause':<16} {'ms':>8}")
    print("-" * 64)
    async with httpx.AsyncClient() as client:
        for group in groups:
            status, cause, ms = await _probe(
                client,
                base=settings.litellm_url,
                key=settings.litellm_master_key,
                model=group,
                structured=False,
            )
            print(f"{group:<28} {str(status or '-'):>6} {cause:<16} {ms:8.0f}")
            if args.structured:
                status, cause, ms = await _probe(
                    client,
                    base=settings.litellm_url,
                    key=settings.litellm_master_key,
                    model=group,
                    structured=True,
                )
                label = f"{group}+json"
                print(f"{label:<28} {str(status or '-'):>6} {cause:<16} {ms:8.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
