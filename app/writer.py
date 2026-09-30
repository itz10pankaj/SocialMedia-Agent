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
        "chosen": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "Array containing exactly 1 chosen item number",
        },
        "angle": {
            "type": "string",
            "description": "One sentence: the practical takeaway or architectural opinion the post should make",
        },
        "style": {
            "type": "string",
            "enum": ["analysis", "deep_dive", "hype_vs_reality"],
            "description": "Format archetype: 'deep_dive' for security/benchmarks/bugs, 'hype_vs_reality' for frameworks/agents/tools, or 'analysis' for releases/general news",
        },
    },
    "required": ["chosen", "angle", "style"],
}

FORMAT_TEMPLATES = {
    "analysis": (
        "Structure your response with these exact 6 numbered parts, separated by blank lines:\n"
        "1. Hook: One punchy, provocative opening sentence that stops the scroll.\n"
        "2. The News: 2-3 sentences explaining the new release, library, or breakthrough in plain developer terms.\n"
        "3. Architectural Impact: 2-3 sentences on what this enables or changes for real software engineering.\n"
        "4. My Take: 2-3 sentences of direct developer perspective or practical advice (in first person).\n"
        "5. Question: One short question inviting fellow developers to share their experience.\n"
        "6. Hashtags: Exactly 3 relevant hashtags on the final line."
    ),
    "deep_dive": (
        "Structure your response with these exact 6 numbered parts, separated by blank lines:\n"
        "1. Hook: A startling technical discovery or counter-intuitive benchmark finding that stops the scroll.\n"
        "2. The Mechanism: 2-3 sentences explaining what was uncovered and how the issue or benchmark works under the hood.\n"
        "3. The Mitigation: 2-3 sentences explaining how to protect against it or properly configure it.\n"
        "4. My Take: 2-3 sentences of direct advice on defensive coding or best practices (in first person).\n"
        "5. Question: One short question inviting engineers to share their debugging experiences.\n"
        "6. Hashtags: Exactly 3 relevant hashtags on the final line."
    ),
    "hype_vs_reality": (
        "Structure your response with these exact 6 numbered parts, separated by blank lines:\n"
        "1. Hook: A sharp, grounding observation that cuts through industry marketing hype.\n"
        "2. Reality Check: 2-3 sentences explaining what this tool actually does versus common misconceptions.\n"
        "3. Production Trade-offs: 2-3 sentences on real engineering costs (latency, memory, maintenance) in production.\n"
        "4. Practical Recommendation: 2-3 sentences on what pragmatic teams should adopt now vs. wait on (in first person).\n"
        "5. Question: One short question asking how readers balance hype with production reliability.\n"
        "6. Hashtags: Exactly 3 relevant hashtags on the final line."
    ),
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


async def pick_topic(items: list[TrendItem], profile: dict) -> tuple[list[TrendItem], str, str, str]:
    prompt = (
        f"I am a {profile['role']}. Below are today's trending tech items:\n\n"
        f"{_items_block(items)}\n\n"
        "Pick the SINGLE best item (by number) that makes the most compelling, practical LinkedIn post "
        "for developers like me.\n"
        "Selection rules:\n"
        "1. MUST be concrete technical news: a major tool release, an architectural benchmark, a security/performance finding, or practical discovery.\n"
        "2. NEVER pick retrospective / anniversary threads (e.g. 'released X years ago'), meme/complaint posts, or beginner question threads.\n"
        "3. Pick ONLY 1 item so the post remains deep, accurate, and tightly focused.\n"
        "4. Choose the best matching style:\n"
        "   - 'deep_dive': for security vulnerabilities, memory bugs, benchmarks, or performance findings.\n"
        "   - 'hype_vs_reality': for new AI agent frameworks, bold claims, or hyped tool launches.\n"
        "   - 'analysis': for library releases, runtime updates, or practical developer news.\n\n"
        'Reply as JSON: {"chosen": [single_number], "angle": "one sentence: practical takeaway", '
        '"style": "analysis" | "deep_dive" | "hype_vs_reality"}'
    )
    raw, _ = await llm.chat([{"role": "user", "content": prompt}], fmt=PICK_SCHEMA, temperature=0.2)
    data = json.loads(raw)
    chosen_raw = data.get("chosen", [])
    if isinstance(chosen_raw, int):
        chosen_raw = [chosen_raw]
    chosen = [items[n - 1] for n in chosen_raw if isinstance(n, int) and 1 <= n <= len(items)][:1]
    if not chosen:
        chosen = items[:1]
    style = data.get("style", "analysis")
    if style not in ("analysis", "deep_dive", "hype_vs_reality"):
        style = "analysis"
    # Form a clean, reliable topic from the chosen item's title
    topic = re.sub(r"\s*\[.*?\]", "", chosen[0].title).strip()
    return chosen, topic, data.get("angle", "").strip(), style


_PART_LABEL = re.compile(
    r"^\s*(\d+\.\s*)?\**(hook|the news|what happened|architectural impact|impact|why it matters|my take|question|hashtags|the mechanism|the core mechanism|the mitigation & fix|the mitigation|reality check|production trade-offs|practical recommendation|takeaway)\**\s*(:|\n|$)\s*",
    re.IGNORECASE | re.MULTILINE,
)


_NUMBER_LABEL = re.compile(r"^\s*\d+\.\s*", re.MULTILINE)


def _ensure_hashtags(text: str, keywords: list[str], count: int = 3) -> str:
    tags = _HASHTAG.findall(text)
    if len(tags) >= count:
        return text
    needed = count - len(tags)
    clean_kws = [f"#{re.sub(r'[^a-zA-Z0-9]', '', kw).capitalize()}" for kw in keywords if kw]
    defaults = ["#SoftwareEngineering", "#TechTrends", "#Programming", "#WebDev", "#AI"]
    candidates = [t for t in clean_kws + defaults if t not in tags and len(t) > 2]
    added = candidates[:needed]
    return f"{text}\n\n{' '.join(added)}"


def _prune_repetition(paragraphs: list[str]) -> list[str]:
    """If a paragraph starts by repeating sentence(s) from the previous paragraph, prune the repetition."""
    if len(paragraphs) < 2:
        return paragraphs

    cleaned = [paragraphs[0]]
    for i in range(1, len(paragraphs)):
        prev = cleaned[-1]
        curr = paragraphs[i]

        prev_sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", prev) if len(s.strip()) > 10]
        curr_sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", curr) if s.strip()]

        while curr_sentences and any(curr_sentences[0].lower() == p.lower() for p in prev_sentences):
            curr_sentences.pop(0)

        if curr_sentences:
            cleaned.append(" ".join(curr_sentences))
    return cleaned


def _clean(text: str) -> str:
    text = text.strip().strip('"').strip()
    text = _PREAMBLE.sub("", text)
    # Strip any echoed prompt sections (e.g. "Facts:\n- Title: ...\n- Source: ...")
    if re.search(r"\b(facts|topic|news to write about)\s*:", text[:120], re.IGNORECASE):
        parts = re.split(r"\n\s*\n", text)
        post_parts = [
            p.strip() for p in parts
            if not re.match(r"^(facts|topic|news to write about|title|source|details|- title|- source|- details)\b", p.strip(), re.IGNORECASE)
        ]
        if post_parts:
            text = "\n\n".join(post_parts)
    text = _PART_LABEL.sub("", text)    # strip structure labels like 'Hook:', 'The News:'
    text = _NUMBER_LABEL.sub("", text)  # strip leading list numbering like '1. ', '2. '
    # Normalize paragraphs separated by blank lines
    raw_paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(raw_paragraphs) <= 2 and text.count("\n") >= 3:
        raw_paragraphs = [p.strip() for p in text.split("\n") if p.strip()]

    # Filter out any standalone label lines that survived
    label_words = {
        "hook", "what happened", "why it matters", "my take", "question", "hashtags",
        "the news", "the mechanism", "the core mechanism", "the mitigation & fix", "the mitigation",
        "reality check", "production trade-offs", "practical recommendation", "architectural impact"
    }
    paragraphs = [p for p in raw_paragraphs if p.lower().strip("*: \t\n") not in label_words]
    paragraphs = _prune_repetition(paragraphs)
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

    # Enforce paragraph separation for LinkedIn readability (minimum 4 paragraphs)
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    if len(paragraphs) < 4:
        problems.append(
            f"needs clear paragraph separation (found {len(paragraphs)} paragraph(s), need at least 4 separated by blank lines)"
        )
    return problems


async def write_post(items: list[TrendItem], config: dict) -> DraftResult:
    profile, post_cfg = config["profile"], config["post"]
    chosen, topic, angle, style = await pick_topic(items, profile)
    log.info("picked topic %r (style=%s) from %s", topic, style, [c.title for c in chosen])

    target = chosen[0]
    facts = f"- Title: {target.title}\n- Source: {target.source}"
    if target.summary:
        facts += f"\n- Details: {target.summary[:400]}"

    template_instructions = FORMAT_TEMPLATES.get(style, FORMAT_TEMPLATES["analysis"])

    system = (
        f"You write high-engagement LinkedIn posts for a {profile['role']}.\n"
        f"Tone: {profile['tone']}.\n\n"
        f"{template_instructions}\n\n"
        "CRITICAL RULES:\n"
        "- Format your output with the 6 numbered parts shown above.\n"
        "- Separate each numbered part with an empty blank line.\n"
        "- DO NOT repeat the opening hook sentence in subsequent paragraphs.\n"
        f"- Focus EXCLUSIVELY on this single story: '{target.title}'. Do NOT mention any other companies, tools, or items from earlier.\n"
        "- The news is about someone else's work: refer to them as 'A developer demonstrated...', 'A new guide shows...', or by the tool name. Never say 'I built' or 'I released' when describing their work.\n"
        "- Stick strictly to the provided facts. Do not invent numbers, benchmarks, or quotes.\n"
        "- No links (URLs). At most 2 emojis total.\n"
        "Output ONLY the 6 numbered post parts."
    )
    user = (
        f"News Story: {target.title}\n"
        f"Source: {target.source}\n"
        f"Details: {target.summary[:350]}\n\n"
        f"Target Angle: {angle}\n\n"
        "Write the 6-part post now:"
    )

    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    text, model, problems = "", "", ["not generated"]
    for attempt in range(1, post_cfg.get("max_attempts", 3) + 1):
        raw, model = await llm.chat(messages)
        text = _clean(raw)
        # Attach hashtags if needed before problem checking to avoid unnecessary retry loops
        text = _ensure_hashtags(text, target.matched_keywords, post_cfg.get("hashtags", 3))
        problems = _problems(text, post_cfg)
        if not problems:
            break
        log.info("attempt %d rejected: %s", attempt, problems)
        messages += [
            {"role": "assistant", "content": raw},
            {
                "role": "user",
                "content": (
                    f"Rewrite it to fix these issues: {'; '.join(problems)}. "
                    "Format as 6 numbered parts separated by blank lines. "
                    "Do not repeat the hook sentence in the body. Output only the post."
                ),
            },
        ]
    if problems:
        log.warning("using draft despite problems: %s", problems)

    return DraftResult(
        text=text,
        topic=topic,
        angle=f"[{style}] {angle}" if style else angle,
        model=model,
        word_count=word_count(text),
        chosen=chosen,
        sources=[{"title": c.title, "url": c.url, "source": c.source} for c in chosen],
    )


async def revise_post(original_text: str, user_instruction: str, topic: str = "") -> str:
    """Use Ollama to rewrite or tweak a post based on conversational user instructions from mobile email."""
    system = (
        "You are an expert LinkedIn ghostwriter. "
        "A user reviewed the draft post and asked for revisions. "
        "Rewrite the post applying their requested changes while preserving high engagement, clear paragraphs, and relevant hashtags.\n"
        "Output ONLY the revised LinkedIn post, without any introductory or concluding meta-commentary."
    )
    user = (
        f"Topic: {topic}\n\n"
        f"Original Post:\n{original_text}\n\n"
        f"User's Revision Request:\n{user_instruction}\n\n"
        "Revised Post:"
    )
    raw, _ = await llm.chat([{"role": "system", "content": system}, {"role": "user", "content": user}])
    return _clean(raw)
