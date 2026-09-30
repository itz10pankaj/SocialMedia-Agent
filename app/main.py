"""Local API server.  Start:  uvicorn app.main:app --port 8000"""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlmodel import select

from app import llm
from app.config import get_settings
from app.db import Draft, DraftStatus, FetchedItem, Run, init_db, session
from app.orchestrator import collect_and_rank, run_pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)
_tasks: set[asyncio.Task] = set()


def _background(coro) -> None:
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def _email_poll_loop():
    """Poll Gmail inbox for replies every 30 seconds in background."""
    while True:
        try:
            from app.inbox import check_email_replies
            await asyncio.to_thread(check_email_replies)
        except Exception as e:
            log.debug("email poll error: %r", e)
        await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    if get_settings().run_on_startup:
        _background(run_pipeline())
    _background(_email_poll_loop())
    yield


app = FastAPI(title="Personal Social Media Agent", lifespan=lifespan)


@app.post("/check-replies")
async def trigger_check_replies():
    """Manually check Gmail inbox for replies right now."""
    from app.inbox import check_email_replies
    results = await asyncio.to_thread(check_email_replies)
    return {"checked": True, "actions": results}


@app.get("/health")
async def health():
    async with httpx.AsyncClient() as client:
        try:
            url, model = await llm.resolve_endpoint(client)
            tags = (await client.get(f"{url}/api/tags", timeout=5)).json()
            installed = [m["name"] for m in tags.get("models", [])]
            ollama = {"url": url, "model": model, "model_installed": model in installed}
        except Exception as e:
            ollama = {"error": str(e)}
    return {"status": "ok", "ollama": ollama}


@app.post("/run")
async def run(force: bool = True, wait: bool = True):
    """Run the pipeline now. force=true ignores the once-per-day rule; wait=false returns immediately."""
    if not wait:
        _background(run_pipeline(force=force))
        return {"started": True}
    return await run_pipeline(force=force)


@app.get("/trends")
async def trends():
    """Preview what the collectors + ranker found, without calling the LLM."""
    items, ranked, status = await collect_and_rank()
    return {"collected": len(items), "sources": status, "ranked": ranked}


class DraftUpdate(BaseModel):
    text: str | None = None
    status: DraftStatus | None = None


@app.get("/drafts")
def list_drafts(limit: int = 20):
    with session() as s:
        return s.exec(select(Draft).order_by(Draft.id.desc()).limit(limit)).all()


@app.get("/drafts/{draft_id}")
def get_draft(draft_id: int):
    with session() as s:
        if not (draft := s.get(Draft, draft_id)):
            raise HTTPException(404, "draft not found")
        return draft


@app.patch("/drafts/{draft_id}")
def update_draft(draft_id: int, payload: DraftUpdate):
    with session() as s:
        draft = s.get(Draft, draft_id)
        if not draft:
            raise HTTPException(404, "draft not found")
        if payload.text is not None:
            draft.text = payload.text
            draft.word_count = len(payload.text.split())
        if payload.status is not None:
            draft.status = payload.status
        s.add(draft)
        s.commit()
        s.refresh(draft)
        return draft


@app.post("/drafts/{draft_id}/send-email")
def email_draft(draft_id: int, to_email: str | None = None):
    with session() as s:
        draft = s.get(Draft, draft_id)
        if not draft:
            raise HTTPException(404, "draft not found")
        from app.mailer import send_draft_email
        success = send_draft_email(draft, to_email=to_email)
        if not success:
            raise HTTPException(500, "Failed to send email. Check GMAIL_ADDRESS and GMAIL_APP_PASSWORD in .env")
        return {"sent": True, "draft_id": draft.id, "recipient": to_email or get_settings().notify_email or get_settings().gmail_address}


@app.post("/drafts/{draft_id}/publish")
def publish_to_linkedin_endpoint(draft_id: int):
    """Publish a draft directly to LinkedIn personal profile."""
    from app.linkedin import publish_draft
    try:
        result = publish_draft(draft_id)
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        log.exception("LinkedIn publishing failed for Draft #%d: %r", draft_id, e)
        raise HTTPException(500, f"LinkedIn publish failed: {e}")


@app.get("/linkedin/status")
def linkedin_status():
    """Check LinkedIn integration status and profile connection."""
    from app.linkedin import get_profile
    settings = get_settings()
    configured = bool(settings.linkedin_access_token)
    if not configured:
        return {"configured": False, "message": "LINKEDIN_ACCESS_TOKEN not configured in .env"}
    try:
        profile = get_profile()
        return {
            "configured": True,
            "connected": True,
            "name": profile.get("name"),
            "email": profile.get("email"),
            "person_urn": profile.get("person_urn"),
        }
    except Exception as e:
        return {"configured": True, "connected": False, "error": str(e)}


@app.get("/runs")
def list_runs(limit: int = 20):
    with session() as s:
        return s.exec(select(Run).order_by(Run.id.desc()).limit(limit)).all()


@app.get("/runs/{run_id}/items")
def run_items(run_id: int, status: str | None = None):
    """Everything fetched in a run. Filter with ?status=sent_to_llm (or chosen, no_keyword_match, ...)."""
    with session() as s:
        q = select(FetchedItem).where(FetchedItem.run_id == run_id)
        if status:
            q = q.where(FetchedItem.status == status)
        return s.exec(q.order_by(FetchedItem.rank_position.is_(None), FetchedItem.rank_position, FetchedItem.rank_score.desc())).all()


static_dir = Path(__file__).resolve().parent / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
