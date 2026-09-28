"""RSS/Atom feeds (tech blogs, dev.to tags, ...)."""
import asyncio
import calendar
import html
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import feedparser
import httpx

from app.models import TrendItem

_TAG = re.compile(r"<[^>]+>")


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAG.sub(" ", text or ""))).strip()


async def _feed(client: httpx.AsyncClient, url: str, since: datetime) -> list[TrendItem]:
    resp = await client.get(url)
    resp.raise_for_status()
    parsed = feedparser.parse(resp.content)

    items = []
    for e in parsed.entries:
        ts = e.get("published_parsed") or e.get("updated_parsed")
        published = datetime.fromtimestamp(calendar.timegm(ts), tz=timezone.utc) if ts else None
        if published and published < since:
            continue
        if not e.get("title") or not e.get("link"):
            continue
        items.append(
            TrendItem(
                source=f"rss:{urlparse(url).netloc}",
                title=_clean(e.title),
                url=e.link,
                summary=_clean(e.get("summary", ""))[:500],
                published_at=published,
            )
        )
    return items


async def collect(client: httpx.AsyncClient, cfg: dict) -> list[TrendItem]:
    since = datetime.now(timezone.utc) - timedelta(hours=cfg.get("lookback_hours", 72))
    results = await asyncio.gather(
        *(_feed(client, url, since) for url in cfg.get("feeds", [])), return_exceptions=True
    )
    items = [i for r in results if not isinstance(r, Exception) for i in r]
    if not items and results and all(isinstance(r, Exception) for r in results):
        raise results[0]
    return items
