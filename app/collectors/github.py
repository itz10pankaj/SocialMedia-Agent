"""New GitHub repos gaining stars fast, via the public search API.

Without a token GitHub allows 10 search requests/minute, which is enough for a few queries a day.
"""
import asyncio
import os
from datetime import date, datetime, timedelta

import httpx

from app.models import TrendItem

API = "https://api.github.com/search/repositories"


async def _query(client: httpx.AsyncClient, query: str, since: date, per_page: int) -> list[TrendItem]:
    headers = {"Accept": "application/vnd.github+json"}
    if token := os.getenv("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    resp = await client.get(
        API,
        params={"q": f"{query} created:>{since.isoformat()}", "sort": "stars", "order": "desc", "per_page": per_page},
        headers=headers,
    )
    resp.raise_for_status()

    return [
        TrendItem(
            source="github",
            title=f"{repo['full_name']}: {repo.get('description') or ''}".strip(": "),
            url=repo["html_url"],
            summary=", ".join(repo.get("topics", [])),
            score=repo.get("stargazers_count", 0),
            published_at=datetime.fromisoformat(repo["created_at"].replace("Z", "+00:00")),
        )
        for repo in resp.json().get("items", [])
    ]


async def collect(client: httpx.AsyncClient, cfg: dict) -> list[TrendItem]:
    since = date.today() - timedelta(days=cfg.get("lookback_days", 7))
    results = await asyncio.gather(
        *(_query(client, q, since, cfg.get("per_query", 15)) for q in cfg.get("queries", [])),
        return_exceptions=True,
    )
    items = [i for r in results if not isinstance(r, Exception) for i in r]
    if not items and results and all(isinstance(r, Exception) for r in results):
        raise results[0]
    return items
