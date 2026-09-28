from datetime import datetime

from pydantic import BaseModel


class TrendItem(BaseModel):
    """One piece of news from any source, in a common shape."""

    source: str              # "hackernews" | "reddit/r/node" | "github" | "rss:<host>"
    title: str
    url: str
    summary: str = ""
    score: float = 0         # upvotes / points / stars (0 when the source has none)
    published_at: datetime | None = None
    # filled in by ranking.py / orchestrator.py
    matched_keywords: list[str] = []
    rank_score: float = 0
    rank_position: int | None = None   # 1..top_n if sent to the LLM
    # what happened to this item: no_keyword_match | duplicate | used_recently | source_cap |
    # below_top_n | sent_to_llm | chosen
    status: str = "new"
