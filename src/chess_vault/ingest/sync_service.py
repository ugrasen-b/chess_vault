from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from chess_vault.db.models import Game
from chess_vault.ingest.chesscom_client import ChessComClient
from chess_vault.ingest.lichess_client import LichessClient
from chess_vault.ingest.normalize import normalize_pgn


@dataclass(frozen=True)
class SyncResult:
    source: str
    fetched: int
    inserted: int
    skipped_existing: int


class SyncService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def sync_lichess(self, username: str, max_games: int = 50) -> SyncResult:
        client = LichessClient()
        pgn_games = client.fetch_user_games_pgn(username=username, max_games=max_games)
        return self._store_games(source="lichess", pgn_games=pgn_games)

    def sync_chesscom(self, username: str, max_months: int = 3) -> SyncResult:
        client = ChessComClient()
        pgn_games = client.fetch_recent_games_pgn(username=username, max_months=max_months)
        return self._store_games(source="chesscom", pgn_games=pgn_games)

    def _store_games(self, source: str, pgn_games: list[str]) -> SyncResult:
        inserted = 0
        skipped = 0

        for raw_pgn in pgn_games:
            normalized = normalize_pgn(source=source, raw_pgn=raw_pgn)

            exists = self.session.execute(
                select(Game.id).where(
                    Game.source == normalized.source,
                    Game.source_game_id == normalized.source_game_id,
                )
            ).first()

            if exists:
                skipped += 1
                continue

            row = Game(
                source=normalized.source,
                source_game_id=normalized.source_game_id,
                white_player=normalized.white_player,
                black_player=normalized.black_player,
                result=normalized.result,
                time_control=normalized.time_control,
                eco=normalized.eco,
                opening=normalized.opening,
                event=normalized.event,
                site=normalized.site,
                played_at=normalized.played_at,
                raw_pgn=normalized.raw_pgn,
            )
            self.session.add(row)
            inserted += 1

        self.session.commit()
        return SyncResult(source=source, fetched=len(pgn_games), inserted=inserted, skipped_existing=skipped)
