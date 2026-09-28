"""Storage: MySQL (DATABASE_URL in .env).

Tables:
  run           one row per pipeline run
  fetched_item  every item collected in a run, with why it was kept or dropped
  draft         generated posts and their approval status
"""
from datetime import datetime, timedelta, timezone
from enum import Enum

from sqlalchemy import Text
from sqlmodel import JSON, Column, Field, Session, SQLModel, create_engine, select

from app.config import get_settings


class DraftStatus(str, Enum):
    PENDING = "PENDING"      # waiting for my approval
    APPROVED = "APPROVED"    # approved, not posted yet (retry on next start if posting failed)
    REJECTED = "REJECTED"
    POSTED = "POSTED"
    EXPIRED = "EXPIRED"      # no reply within 48 h


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# MySQL needs a length for every VARCHAR; long text uses TEXT columns.

class Run(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None
    status: str = Field(default="RUNNING", max_length=20)  # RUNNING | OK | SKIPPED | FAILED
    items_collected: int = 0
    items_ranked: int = 0
    sources_status: dict = Field(default_factory=dict, sa_column=Column(JSON))  # {"reddit": "100 items", ...}
    draft_id: int | None = None
    message: str = Field(default="", sa_column=Column(Text))


class FetchedItem(SQLModel, table=True):
    __tablename__ = "fetched_item"

    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="run.id", index=True)
    source: str = Field(max_length=100, index=True)
    title: str = Field(max_length=500)
    url: str = Field(max_length=1000)
    summary: str = Field(default="", sa_column=Column(Text))
    score: float = 0
    published_at: datetime | None = None
    matched_keywords: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    rank_score: float = 0
    rank_position: int | None = None
    status: str = Field(default="new", max_length=30, index=True)


class Draft(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    run_id: int | None = Field(default=None, foreign_key="run.id", index=True)
    created_at: datetime = Field(default_factory=utcnow, index=True)
    status: DraftStatus = DraftStatus.PENDING
    text: str = Field(sa_column=Column(Text, nullable=False))
    topic: str = Field(default="", max_length=300)
    angle: str = Field(default="", sa_column=Column(Text))
    model: str = Field(default="", max_length=100)
    word_count: int = 0
    sources: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    linkedin_post_id: str | None = Field(default=None, max_length=200)
    posted_at: datetime | None = None


_engine = None


def get_engine():
    global _engine
    if _engine is None:
        # pool_pre_ping: reconnect cleanly if MySQL dropped an idle connection
        _engine = create_engine(get_settings().database_url, pool_pre_ping=True, pool_recycle=3600)
    return _engine


def init_db() -> None:
    SQLModel.metadata.create_all(get_engine())


def session() -> Session:
    return Session(get_engine())


def draft_created_today(s: Session) -> Draft | None:
    # "Today" is local time: that's what matters for a once-per-day post.
    local_midnight = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    since = local_midnight.astimezone(timezone.utc)
    return s.exec(select(Draft).where(Draft.created_at >= since)).first()


def recently_used_urls(s: Session, days: int) -> set[str]:
    since = utcnow() - timedelta(days=days)
    drafts = s.exec(select(Draft).where(Draft.created_at >= since)).all()
    return {src["url"] for d in drafts for src in d.sources if "url" in src}
