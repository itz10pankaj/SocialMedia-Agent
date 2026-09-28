"""Hacker News via the public Algolia API (no key needed)."""
import time
from datetime import datetime, timezone

import httpx

from app.models import TrendItem

API = "https://hn.algolia.com/api/v1/search"


async def collect(client: httpx.AsyncClient, cfg: dict) -> list[TrendItem]:
    since = int(time.time()) - cfg.get("lookback_hours", 48) * 3600
    params = {
        "tags": "story",
        "numericFilters": f"created_at_i>{since},points>{cfg.get('min_points', 40)}",
        "hitsPerPage": cfg.get("max_items", 100),
    }
    resp = await client.get(API, params=params)
    resp.raise_for_status()

    items = []
    for hit in resp.json().get("hits", []):
        if not hit.get("title"):
            continue
        items.append(
            TrendItem(
                source="hackernews",
                title=hit["title"],
                url=hit.get("url") or f"https://news.ycombinator.com/item?id={hit['objectID']}",
                summary=(hit.get("story_text") or "")[:500],
                score=hit.get("points") or 0,
                published_at=datetime.fromtimestamp(hit["created_at_i"], tz=timezone.utc),
            )
        )
    return items
