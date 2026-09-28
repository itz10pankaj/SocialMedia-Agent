"""Run all enabled collectors concurrently. One failing source never breaks the others."""
import asyncio
import logging

import httpx

from app.collectors import github, hackernews, reddit, rss
from app.models import TrendItem

log = logging.getLogger(__name__)

COLLECTORS = {
    "hackernews": hackernews.collect,
    "reddit": reddit.collect,
    "github": github.collect,
    "rss": rss.collect,
}

USER_AGENT = "PersonalSocialAgent/0.1 (personal trend reader)"


async def collect_all(sources_cfg: dict) -> tuple[list[TrendItem], dict[str, str]]:
    """Returns (items, per-source status like {'reddit': '87 items'} or {'rss': 'error: ...'})."""
    enabled = {name: fn for name, fn in COLLECTORS.items() if sources_cfg.get(name, {}).get("enabled")}
    async with httpx.AsyncClient(
        timeout=20, follow_redirects=True, headers={"User-Agent": USER_AGENT}
    ) as client:
        results = await asyncio.gather(
            *(fn(client, sources_cfg[name]) for name, fn in enabled.items()), return_exceptions=True
        )

    items: list[TrendItem] = []
    status: dict[str, str] = {}
    for name, result in zip(enabled, results):
        if isinstance(result, Exception):
            log.warning("collector %s failed: %r", name, result)
            status[name] = f"error: {result!r}"[:200]
        else:
            items.extend(result)
            status[name] = f"{len(result)} items"
    return items, status
