from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass

import chess
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from chess_vault.analysis.analyze_service import extract_position_boundaries
from chess_vault.db.models import Game, IndexedGame, PositionOccurrence


def position_key_from_fen(fen: str) -> str:
    return " ".join(fen.split(" ")[:4])


def index_game_occurrences(game: Game) -> list[PositionOccurrence]:
    boundaries = extract_position_boundaries(game.raw_pgn)
    occurrences: list[PositionOccurrence] = []
    for boundary, next_boundary in zip(boundaries, boundaries[1:]):
        move = chess.Move.from_uci(next_boundary.move_uci)
        san = chess.Board(boundary.fen).san(move)
        occurrences.append(
            PositionOccurrence(
                position_key=position_key_from_fen(boundary.fen),
                game_id=game.id,
                ply=boundary.ply,
                turn="w" if boundary.turn == chess.WHITE else "b",
                move_uci=next_boundary.move_uci,
                move_san=san,
            )
        )
    return occurrences


@dataclass(frozen=True)
class IndexSummary:
    games_indexed: int
    occurrences_inserted: int


class PositionIndexService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def index_unindexed_games(
        self,
        batch_commit_every: int = 200,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> IndexSummary:
        indexed_game_ids = select(IndexedGame.game_id)
        game_ids = (
            self.session.execute(select(Game.id).where(Game.id.notin_(indexed_game_ids)))
            .scalars()
            .all()
        )

        games_indexed = 0
        occurrences_inserted = 0
        for index, game_id in enumerate(game_ids, start=1):
            game = self.session.get(Game, game_id)
            if game is None:
                continue
            occurrences = index_game_occurrences(game)
            for occurrence in occurrences:
                self.session.add(occurrence)
            self.session.add(IndexedGame(game_id=game_id))
            occurrences_inserted += len(occurrences)
            games_indexed += 1

            if index % batch_commit_every == 0:
                self.session.commit()
            if on_progress:
                on_progress(index, len(game_ids))

        self.session.commit()
        return IndexSummary(games_indexed=games_indexed, occurrences_inserted=occurrences_inserted)


@dataclass(frozen=True)
class NextMoveStat:
    move_uci: str
    move_san: str
    games: int
    white_wins: int
    black_wins: int
    draws: int


@dataclass(frozen=True)
class ExplorerStats:
    position_key: str
    fen: str
    total_games: int
    white_wins: int
    black_wins: int
    draws: int
    next_moves: list[NextMoveStat]


def _tally(result: str | None, counts: dict[str, int]) -> None:
    if result == "1-0":
        counts["white_wins"] += 1
    elif result == "0-1":
        counts["black_wins"] += 1
    elif result == "1/2-1/2":
        counts["draws"] += 1


def lookup_position(session: Session, player: str, moves: list[str]) -> ExplorerStats:
    norm_player = player.strip().lower()
    board = chess.Board()
    for token in moves:
        board.push_san(token)

    position_key = position_key_from_fen(board.fen())

    rows = session.execute(
        select(PositionOccurrence.move_uci, PositionOccurrence.move_san, Game.result)
        .join(Game, Game.id == PositionOccurrence.game_id)
        .where(
            PositionOccurrence.position_key == position_key,
            or_(
                func.lower(Game.white_player) == norm_player,
                func.lower(Game.black_player) == norm_player,
            ),
        )
    ).all()

    total_counts = {"white_wins": 0, "black_wins": 0, "draws": 0}
    by_move: dict[tuple[str, str], dict[str, int]] = defaultdict(
        lambda: {"games": 0, "white_wins": 0, "black_wins": 0, "draws": 0}
    )

    for move_uci, move_san, result in rows:
        _tally(result, total_counts)
        move_counts = by_move[(move_uci, move_san)]
        move_counts["games"] += 1
        _tally(result, move_counts)

    next_moves = [
        NextMoveStat(
            move_uci=move_uci,
            move_san=move_san,
            games=counts["games"],
            white_wins=counts["white_wins"],
            black_wins=counts["black_wins"],
            draws=counts["draws"],
        )
        for (move_uci, move_san), counts in by_move.items()
    ]
    next_moves.sort(key=lambda stat: (-stat.games, stat.move_san))

    return ExplorerStats(
        position_key=position_key,
        fen=board.fen(),
        total_games=len(rows),
        white_wins=total_counts["white_wins"],
        black_wins=total_counts["black_wins"],
        draws=total_counts["draws"],
        next_moves=next_moves,
    )
