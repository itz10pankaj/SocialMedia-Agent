"""Thin client for Ollama's HTTP API.

Switching to laptop B = change OLLAMA_URL in .env. If the primary server is unreachable,
the fallback (e.g. a small model on this laptop) is used automatically.
"""
import logging

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)


class LLMUnavailable(RuntimeError):
    pass


async def _reachable(client: httpx.AsyncClient, url: str) -> bool:
    try:
        r = await client.get(f"{url}/api/version", timeout=3)
        return r.status_code == 200
    except httpx.HTTPError:
        return False


async def resolve_endpoint(client: httpx.AsyncClient) -> tuple[str, str]:
    """Returns (url, model) of the first reachable Ollama server."""
    s = get_settings()
    candidates = [(s.ollama_url, s.ollama_model)]
    if s.ollama_fallback_url and (s.ollama_fallback_url, s.ollama_fallback_model) != candidates[0]:
        candidates.append((s.ollama_fallback_url, s.ollama_fallback_model or s.ollama_model))
    for url, model in candidates:
        if await _reachable(client, url.rstrip("/")):
            if url != s.ollama_url:
                log.warning("primary Ollama %s unreachable, using fallback %s (%s)", s.ollama_url, url, model)
            return url.rstrip("/"), model
    raise LLMUnavailable(f"No Ollama server reachable (tried {[c[0] for c in candidates]})")


async def chat(messages: list[dict], *, fmt: dict | None = None, temperature: float = 0.7) -> tuple[str, str]:
    """Send a chat request. Returns (reply_text, model_used)."""
    async with httpx.AsyncClient(timeout=600) as client:
        url, model = await resolve_endpoint(client)
        body = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_ctx": 4096},
        }
        if fmt:
            body["format"] = fmt
        r = await client.post(f"{url}/api/chat", json=body)
        r.raise_for_status()
        return r.json()["message"]["content"], model
