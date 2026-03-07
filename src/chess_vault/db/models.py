from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
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


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player: Mapped[str] = mapped_column(String(80), nullable=False)
    source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    engine_name: Mapped[str] = mapped_column(String(64), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(128), nullable=False, default="unknown")
    depth: Mapped[int] = mapped_column(Integer, nullable=False)
    win_threshold_cp: Mapped[int] = mapped_column(Integer, nullable=False)
    drop_to_cp: Mapped[int] = mapped_column(Integer, nullable=False)
    lookahead_plies: Mapped[int] = mapped_column(Integer, nullable=False)
    games_scanned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mistakes_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)


class EngineEval(Base):
    __tablename__ = "engine_evals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fen: Mapped[str] = mapped_column(Text, nullable=False)
    depth: Mapped[int] = mapped_column(Integer, nullable=False)
    engine_name: Mapped[str] = mapped_column(String(64), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(128), nullable=False, default="unknown")
    score_cp: Mapped[int] = mapped_column(Integer, nullable=False)
    best_move_uci: Mapped[str | None] = mapped_column(String(16), nullable=True)
    pv: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "fen",
            "depth",
            "engine_name",
            "engine_version",
            name="uq_engine_eval_key",
        ),
    )


class GameMistake(Base):
    __tablename__ = "game_mistakes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id"), nullable=False)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"), nullable=False)
    player: Mapped[str] = mapped_column(String(80), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    ply: Mapped[int] = mapped_column(Integer, nullable=False)
    fen: Mapped[str] = mapped_column(Text, nullable=False)
    move_uci: Mapped[str] = mapped_column(String(16), nullable=False)
    before_eval_cp: Mapped[int] = mapped_column(Integer, nullable=False)
    after_eval_cp: Mapped[int] = mapped_column(Integer, nullable=False)
    swing_cp: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), server_default=func.now(), nullable=False
    )
