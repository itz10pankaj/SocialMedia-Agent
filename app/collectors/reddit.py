"""Reddit top posts via the public RSS feed (no key needed).

- Reddit's public JSON API returns 403 without OAuth, but RSS still works.
- Anonymous requests are rate-limited, so all subreddits are fetched in ONE request
  (r/a+b+c), i.e. one Reddit request per daily run.
- RSS has no upvote counts, so popularity comes from position in the "top" list.
"""
import asyncio
import calendar
import logging
from datetime import datetime, timezone

import feedparser
import httpx

from app.collectors.rss import _clean
from app.models import TrendItem

log = logging.getLogger(__name__)


async def collect(client: httpx.AsyncClient, cfg: dict) -> list[TrendItem]:
    subs = cfg.get("subreddits", [])
    if not subs:
        return []
    limit = min(cfg.get("per_subreddit", 25) * len(subs), 100)
    url = f"https://www.reddit.com/r/{'+'.join(subs)}/top/.rss"
    params = {"t": cfg.get("time_filter", "day"), "limit": limit}

    resp = await client.get(url, params=params)
    if resp.status_code == 429:  # one polite retry
        log.info("reddit rate-limited, retrying in 15 s")
        await asyncio.sleep(15)
        resp = await client.get(url, params=params)
    resp.raise_for_status()
    parsed = feedparser.parse(resp.content)

    items = []
    for position, e in enumerate(parsed.entries):
        ts = e.get("published_parsed") or e.get("updated_parsed")
        content = e.get("content", [{}])[0].get("value", "") or e.get("summary", "")
        sub = e.get("tags", [{}])[0].get("term", "") if e.get("tags") else ""
        items.append(
            TrendItem(
                source=f"reddit/r/{sub}" if sub else "reddit",
                title=_clean(e.get("title", "")),
                url=e.get("link", ""),
                summary=_clean(content).replace("submitted by", "").strip()[:500],
                score=limit - position,  # 1st in "top" list = most popular
                published_at=datetime.fromtimestamp(calendar.timegm(ts), tz=timezone.utc) if ts else None,
            )
        )
    return [i for i in items if i.title and i.url]
