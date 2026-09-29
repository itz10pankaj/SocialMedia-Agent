"""Filter items by my stack, dedupe, and rank. Plain Python, no AI needed."""
import math
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from app.models import TrendItem

MAX_PER_SOURCE = 4  # keep the LLM's input diverse
QUESTION_PENALTY = 0.2
RETROSPECTIVE_PENALTY = 0.35

_RETRO_PATTERN = re.compile(
    r"\b(?:released|launched|announced|started)\s+\d+\s+(?:years?|months?)\s+ago\b|"
    r"\b(?:anniversary|retrospective|looking back)\b",
    re.IGNORECASE,
)
_QUESTION_START = re.compile(
    r"^(how (to|do|can|would)|why (is|do|does)|anyone|is it|what is)\b",
    re.IGNORECASE,
)


def _keyword_patterns(keywords: list[str]) -> list[tuple[str, re.Pattern]]:
    # whole-word match; lookarounds so "llama" doesn't match inside "ollama"
    return [(kw, re.compile(rf"(?<![\w]){re.escape(kw.lower())}(?![\w])")) for kw in keywords]


def _norm_url(url: str) -> str:
    p = urlparse(url)
    return (p.netloc.removeprefix("www.") + p.path.rstrip("/")).lower()


def _norm_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def _source_family(source: str) -> str:
    return re.split(r"[/:]", source)[0]


def rank(items: list[TrendItem], keywords: list[str], top_n: int, exclude_urls: set[str] = frozenset()) -> list[TrendItem]:
    patterns = _keyword_patterns(keywords)
    excluded = {_norm_url(u) for u in exclude_urls}

    # 1. keep only items about my stack, dedupe by URL and title
    # (every item gets a .status so the DB shows why it was kept or dropped)
    seen_urls, seen_titles, kept = set(), set(), []
    for item in items:
        title = item.title.lower()
        text = f"{title} {item.summary.lower()}"
        item.matched_keywords = [kw for kw, pat in patterns if pat.search(text)]
        # relevant = keyword in the title, or at least 2 keywords in the body (one passing mention isn't enough)
        in_title = any(pat.search(title) for _, pat in patterns)
        if not (in_title or len(item.matched_keywords) >= 2):
            item.status = "no_keyword_match"
            continue
        u, t = _norm_url(item.url), _norm_title(item.title)
        if u in excluded:
            item.status = "used_recently"
            continue
        if u in seen_urls or t in seen_titles:
            item.status = "duplicate"
            continue
        seen_urls.add(u)
        seen_titles.add(t)
        kept.append(item)

    # 2. score: popularity (relative to its own source, since HN points != GitHub stars), freshness, relevance
    max_score: dict[str, float] = {}
    for item in kept:
        max_score[item.source] = max(max_score.get(item.source, 0), item.score)

    now = datetime.now(timezone.utc)
    for item in kept:
        top = max_score[item.source]
        popularity = math.log1p(item.score) / math.log1p(top) if top > 0 else 0.3
        if item.published_at:
            age_h = max((now - item.published_at).total_seconds() / 3600, 0)
            freshness = 0.5 ** (age_h / 24)  # halves every 24 h
        else:
            freshness = 0.3
        relevance = min(len(item.matched_keywords), 3) / 3
        score = 0.5 * popularity + 0.3 * freshness + 0.2 * relevance
        if item.title.rstrip().endswith("?") or _QUESTION_START.search(item.title):
            score -= QUESTION_PENALTY  # "how do you...?" threads make weaker posts than actual news
        if _RETRO_PATTERN.search(item.title):
            score -= RETROSPECTIVE_PENALTY  # retrospective / anniversary threads rank lower than fresh news
        item.rank_score = round(score, 4)

    # 3. best first, capped per source family
    kept.sort(key=lambda i: i.rank_score, reverse=True)
    per_family: dict[str, int] = {}
    result = []
    for item in kept:
        if len(result) >= top_n:
            item.status = "below_top_n"
            continue
        fam = _source_family(item.source)
        if per_family.get(fam, 0) >= MAX_PER_SOURCE:
            item.status = "source_cap"
            continue
        per_family[fam] = per_family.get(fam, 0) + 1
        result.append(item)
        item.status, item.rank_position = "sent_to_llm", len(result)
    return result
