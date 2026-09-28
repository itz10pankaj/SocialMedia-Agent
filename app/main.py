"""Local API server.  Start:  uvicorn app.main:app --port 8000"""
import asyncio
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException
from sqlmodel import select

from app import llm
from app.config import get_settings
from app.db import Draft, FetchedItem, Run, init_db, session
from app.orchestrator import collect_and_rank, run_pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)
_tasks: set[asyncio.Task] = set()


def _background(coro) -> None:
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    if get_settings().run_on_startup:
        _background(run_pipeline())
    yield


app = FastAPI(title="Personal Social Media Agent", lifespan=lifespan)


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
