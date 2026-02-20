from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from chess_vault.config import get_settings
from chess_vault.db.models import Base


def _ensure_sqlite_parent_exists(db_url: str) -> None:
    prefix = "sqlite:///"
    if not db_url.startswith(prefix):
        return
    rel_path = db_url.removeprefix(prefix)
    path = Path(rel_path)
    if path.parent and str(path.parent) != ".":
        path.parent.mkdir(parents=True, exist_ok=True)


def make_engine(echo: bool = False):
    settings = get_settings()
    _ensure_sqlite_parent_exists(settings.db_url)
    return create_engine(settings.db_url, echo=echo, future=True)


def make_session_factory(echo: bool = False):
    engine = make_engine(echo=echo)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db(echo: bool = False) -> None:
    engine = make_engine(echo=echo)
    Base.metadata.create_all(bind=engine)
