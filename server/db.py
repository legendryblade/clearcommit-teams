"""Database engine, sessions, and the RLS row context hook.

The API is the only database client. Authorization is enforced in the API
layer for every query (works identically on SQLite and PostgreSQL), and on
PostgreSQL the verified caller id is additionally pinned to the transaction
so row-level security policies can act as defense in depth.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import Settings


def create_db_engine(settings: Settings) -> Engine:
    url = settings.database_url
    kwargs: dict = {"future": True, "pool_pre_ping": not url.startswith("sqlite")}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, **kwargs)
    return engine


def make_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def set_row_context(session: Session, user_id: str) -> None:
    """Pin the verified caller id for PostgreSQL RLS within this transaction."""
    bind = session.get_bind()
    if bind.dialect.name == "postgresql":
        session.execute(
            text("SELECT set_config('app.user_id', :uid, true)"),
            {"uid": user_id},
        )


def session_scope(factory: sessionmaker, user_id: str | None = None) -> Iterator[Session]:
    session = factory()
    try:
        if user_id:
            set_row_context(session, user_id)
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
