from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    source_game_id: Mapped[str] = mapped_column(String(255), nullable=False)

    white_player: Mapped[str | None] = mapped_column(String(80), nullable=True)
    black_player: Mapped[str | None] = mapped_column(String(80), nullable=True)
    result: Mapped[str | None] = mapped_column(String(16), nullable=True)
    time_control: Mapped[str | None] = mapped_column(String(64), nullable=True)
    eco: Mapped[str | None] = mapped_column(String(16), nullable=True)
    opening: Mapped[str | None] = mapped_column(String(255), nullable=True)
    event: Mapped[str | None] = mapped_column(String(255), nullable=True)
    site: Mapped[str | None] = mapped_column(String(255), nullable=True)
    played_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)

    raw_pgn: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (UniqueConstraint("source", "source_game_id", name="uq_game_source_source_id"),)


class SyncState(Base):
    __tablename__ = "sync_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    username: Mapped[str] = mapped_column(String(80), nullable=False)
    cursor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (UniqueConstraint("source", "username", name="uq_sync_state_source_username"),)
