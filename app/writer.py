"""Turns ranked trend items into a LinkedIn post draft using the local LLM.

Two small steps work better than one big prompt for a 3B model:
  1. pick 1-2 related items and an angle (structured JSON output)
  2. write the post about just those items
"""
import json
import logging
import re
from dataclasses import dataclass, field

from app import llm
from app.models import TrendItem

log = logging.getLogger(__name__)

PICK_SCHEMA = {
    "type": "object",
    "properties": {
        "chosen": {"type": "array", "items": {"type": "integer"}},
        "topic": {"type": "string"},
        "angle": {"type": "string"},
    },
    "required": ["chosen", "topic", "angle"],
}

_PREAMBLE = re.compile(r"^(sure|here('s| is)|certainly|okay|ok)\b[^\n]*\n+", re.IGNORECASE)
_HASHTAG = re.compile(r"#\w[\w.]*")


@dataclass
class DraftResult:
    text: str
    topic: str
    angle: str
    model: str
    word_count: int
    chosen: list[TrendItem] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)


def word_count(text: str) -> int:
    return len(_HASHTAG.sub("", text).split())


def _items_block(items: list[TrendItem]) -> str:
    lines = []
    for i, it in enumerate(items, 1):
        summary = f" | {it.summary[:200]}" if it.summary else ""
        lines.append(f"{i}. [{it.source}] {it.title}{summary}")
    return "\n".join(lines)


async def pick_topic(items: list[TrendItem], profile: dict) -> tuple[list[TrendItem], str, str]:
    prompt = (
        f"I am a {profile['role']}. Below are today's trending tech items.\n\n"
        f"{_items_block(items)}\n\n"
        "Pick the 1 or 2 items (by number) that would make the most interesting LinkedIn post for "
        "developers like me. Prefer concrete news (a release, a tool, a finding) over opinion threads. "
        "If you pick 2, they must be about the same theme.\n"
        'Reply as JSON: {"chosen": [numbers], "topic": "3-8 word topic", '
        '"angle": "one sentence: the practical takeaway or opinion the post should make"}'
    )
    raw, _ = await llm.chat([{"role": "user", "content": prompt}], fmt=PICK_SCHEMA, temperature=0.3)
    data = json.loads(raw)
    chosen = [items[n - 1] for n in data.get("chosen", []) if isinstance(n, int) and 1 <= n <= len(items)][:2]
    if not chosen:
        chosen = items[:1]
    return chosen, data.get("topic", "").strip(), data.get("angle", "").strip()


_PART_LABEL = re.compile(
    r"^\s*(\d\.\s*)?\**(hook|what happened|why it matters|my take|question|hashtags)\**\s*:\s*",
    re.IGNORECASE | re.MULTILINE,
)


def _clean(text: str) -> str:
    text = text.strip().strip('"').strip()
    text = _PREAMBLE.sub("", text)
    text = _PART_LABEL.sub("", text)  # small models sometimes echo the structure labels
    # one blank line between paragraphs (LinkedIn readability)
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n|\n", text) if p.strip()]
    return "\n\n".join(paragraphs)


def _problems(text: str, post_cfg: dict) -> list[str]:
    words = word_count(text)
    tags = len(_HASHTAG.findall(text))
    problems = []
    if words < post_cfg["min_words"]:
        problems.append(f"too short ({words} words, need at least {post_cfg['min_words']})")
    if words > post_cfg["max_words"]:
        problems.append(f"too long ({words} words, max {post_cfg['max_words']})")
    if tags == 0:
        problems.append("no hashtags")
    if "http" in text:
        problems.append("contains a link")
    return problems


async def write_post(items: list[TrendItem], config: dict) -> DraftResult:
    profile, post_cfg = config["profile"], config["post"]
    chosen, topic, angle = await pick_topic(items, profile)
    log.info("picked topic %r from %s", topic, [c.title for c in chosen])

    facts = "\n".join(f"- {c.title}" + (f"\n  Details: {c.summary[:400]}" if c.summary else "") for c in chosen)
    # Small models ignore word counts but follow an explicit paragraph structure well.
    system = (
        f"You write LinkedIn posts for a {profile['role']}. Tone: {profile['tone']}.\n"
        "Write the post with exactly this structure, separating parts with a blank line:\n"
        "1. Hook: one punchy sentence that makes developers stop scrolling.\n"
        "2. What happened: 2-3 sentences explaining the news in plain words.\n"
        "3. Why it matters: 2-3 sentences on the impact for developers building real products.\n"
        "4. My take: 2-3 sentences of practical advice or opinion, in first person.\n"
        "5. Question: one short question inviting readers to share their experience.\n"
        f"6. Hashtags: exactly {post_cfg['hashtags']} relevant hashtags on one line.\n"
        "Rules: the news is about OTHER people's work, so never say 'I made/built/released' it; "
        "original wording (never copy the source); only use the facts given, never invent numbers, "
        "versions or quotes; no links; at most 2 emojis; no headings or part labels. "
        "Output only the post text."
    )
    user = f"Topic: {topic}\nAngle: {angle}\n\nFacts:\n{facts}"

    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    text, model, problems = "", "", ["not generated"]
    for attempt in range(1, post_cfg.get("max_attempts", 3) + 1):
        raw, model = await llm.chat(messages)
        text = _clean(raw)
        problems = _problems(text, post_cfg)
        if not problems:
            break
        log.info("attempt %d rejected: %s", attempt, problems)
        messages += [
            {"role": "assistant", "content": raw},
            {
                "role": "user",
                "content": f"Rewrite it. Problems: {'; '.join(problems)}. Follow all 6 parts of the structure, "
                "with 2-3 full sentences in parts 2, 3 and 4. Output only the post.",
            },
        ]
    if problems:
        log.warning("using draft despite problems: %s", problems)

    return DraftResult(
        text=text,
        topic=topic,
        angle=angle,
        model=model,
        word_count=word_count(text),
        chosen=chosen,
        sources=[{"title": c.title, "url": c.url, "source": c.source} for c in chosen],
    )
