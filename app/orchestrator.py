"""The daily pipeline: collect -> rank -> write -> save draft.

Run from the terminal without the server:  python -m app.orchestrator [--force]
"""
import asyncio
import logging
import sys

from app.collectors import collect_all
from app.config import get_config
from sqlmodel import select

from app.db import Draft, FetchedItem, Run, draft_created_today, init_db, recently_used_urls, session, utcnow
from app.models import TrendItem
from app.ranking import rank
from app.writer import write_post
from app.mailer import send_draft_email

log = logging.getLogger(__name__)
_lock = asyncio.Lock()


async def collect_and_rank() -> tuple[list[TrendItem], list[TrendItem], dict[str, str]]:
    cfg = get_config()
    items, status = await collect_all(cfg["sources"])
    with session() as s:
        used = recently_used_urls(s, cfg["ranking"]["avoid_repeat_days"])
    ranked = rank(items, cfg["stack_keywords"], cfg["ranking"]["top_n"], used)
    return items, ranked, status


def _save_items(run_id: int, items: list[TrendItem]) -> None:
    with session() as s:
        s.add_all(
            FetchedItem(
                run_id=run_id,
                source=i.source[:100],
                title=i.title[:500],
                url=i.url[:1000],
                summary=i.summary,
                score=i.score,
                published_at=i.published_at,
                matched_keywords=i.matched_keywords,
                rank_score=i.rank_score,
                rank_position=i.rank_position,
                status=i.status,
            )
            for i in items
        )
        s.commit()


def _mark_chosen(run_id: int, urls: list[str]) -> None:
    with session() as s:
        rows = s.exec(
            select(FetchedItem).where(FetchedItem.run_id == run_id, FetchedItem.url.in_([u[:1000] for u in urls]))
        ).all()
        for row in rows:
            row.status = "chosen"
            s.add(row)
        s.commit()


async def run_pipeline(force: bool = False) -> Run:
    """force=True skips the once-per-day check (for development)."""
    async with _lock:  # never run two pipelines at once
        with session() as s:
            run = Run()
            if not force and (existing := draft_created_today(s)):
                run.status, run.draft_id = "SKIPPED", existing.id
                run.message = f"draft #{existing.id} already created today"
                run.finished_at = utcnow()
                s.add(run)
                s.commit()
                s.refresh(run)
                log.info(run.message)
                return run
            s.add(run)
            s.commit()
            s.refresh(run)

        try:
            items, ranked, status = await collect_and_rank()
            run.items_collected, run.items_ranked, run.sources_status = len(items), len(ranked), status
            log.info("collected %d items %s, %d relevant after ranking", len(items), status, len(ranked))
            # saved before the LLM step, so the fetched data is kept even if writing fails
            _save_items(run.id, items)
            if not ranked:
                raise RuntimeError(f"no relevant items found (sources: {status})")

            result = await write_post(ranked, get_config())
            draft = Draft(
                run_id=run.id,
                text=result.text,
                topic=result.topic[:300],
                angle=result.angle,
                model=result.model,
                word_count=result.word_count,
                sources=result.sources,
            )
            with session() as s:
                s.add(draft)
                s.commit()
                s.refresh(draft)
            _mark_chosen(run.id, [c.url for c in result.chosen])
            email_sent = send_draft_email(draft)
            email_note = " (email sent)" if email_sent else ""
            run.status, run.draft_id = "OK", draft.id
            run.message = f"draft #{draft.id}: {result.topic}{email_note}"
        except Exception as e:
            log.exception("pipeline failed")
            run.status, run.message = "FAILED", repr(e)[:500]

        run.finished_at = utcnow()
        with session() as s:
            s.add(run)
            s.commit()
            s.refresh(run)
        return run


def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    init_db()
    run = asyncio.run(run_pipeline(force="--force" in sys.argv))
    print(f"\nRun {run.status}: {run.message}")
    if run.draft_id:
        with session() as s:
            draft = s.get(Draft, run.draft_id)
            print(f"\n----- Draft #{draft.id} ({draft.model}, {draft.word_count} words) -----\n{draft.text}\n\nSources:")
            for src in draft.sources:
                print(f"  - {src['title']}\n    {src['url']}")


if __name__ == "__main__":
    _main()
