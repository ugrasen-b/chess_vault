from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import chess
from sqlalchemy import select
from sqlalchemy.orm import Session

from chess_vault.analysis.explorer import position_key_from_fen
from chess_vault.db.models import Repertoire, RepertoireMove


@dataclass(frozen=True)
class BookMove:
    move_uci: str
    move_san: str
    comment: str | None


@dataclass(frozen=True)
class Deviation:
    ply: int
    position_key: str
    played_uci: str
    played_san: str
    expected: list[BookMove]


def san_line_to_uci(sans: list[str]) -> list[str]:
    """Convert SAN moves from the start position into UCI strings."""
    board = chess.Board()
    ucis: list[str] = []
    for san in sans:
        move = board.push_san(san)
        ucis.append(move.uci())
    return ucis


class RepertoireService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_repertoires(self) -> list[Repertoire]:
        return list(
            self.session.execute(select(Repertoire).order_by(Repertoire.name)).scalars().all()
        )

    def get_repertoire(self, repertoire_id: int) -> Repertoire | None:
        return self.session.get(Repertoire, repertoire_id)

    def create_repertoire(self, name: str, side: str = "both") -> Repertoire:
        repertoire = Repertoire(name=name.strip(), side=side)
        self.session.add(repertoire)
        self.session.commit()
        return repertoire

    def add_line(
        self,
        repertoire_id: int,
        uci_moves: list[str],
        comment_by_index: dict[int, str] | None = None,
    ) -> int:
        """Persist one line (a sequence of UCI moves from the start position) into the
        repertoire tree. Each move becomes a node keyed by the position before it.
        Re-saving the same node updates its comment instead of duplicating. Returns the
        number of nodes inserted or updated."""
        comment_by_index = comment_by_index or {}
        board = chess.Board()
        touched = 0
        for index, uci in enumerate(uci_moves):
            move = chess.Move.from_uci(uci)
            san = board.san(move)
            position_key = position_key_from_fen(board.fen())
            comment = (comment_by_index.get(index) or "").strip() or None

            existing = self.session.execute(
                select(RepertoireMove).where(
                    RepertoireMove.repertoire_id == repertoire_id,
                    RepertoireMove.position_key == position_key,
                    RepertoireMove.move_uci == uci,
                )
            ).scalar_one_or_none()
            if existing is None:
                self.session.add(
                    RepertoireMove(
                        repertoire_id=repertoire_id,
                        position_key=position_key,
                        move_uci=uci,
                        move_san=san,
                        comment=comment,
                    )
                )
            elif comment is not None:
                existing.comment = comment
            touched += 1

            board.push(move)

        self.session.commit()
        return touched

    def book_moves_at(self, repertoire_id: int, position_key: str) -> list[BookMove]:
        rows = self.session.execute(
            select(RepertoireMove).where(
                RepertoireMove.repertoire_id == repertoire_id,
                RepertoireMove.position_key == position_key,
            )
        ).scalars().all()
        return [BookMove(r.move_uci, r.move_san, r.comment) for r in rows]

    def load_book(self, repertoire_id: int) -> dict[str, list[BookMove]]:
        """Load the whole repertoire into a {position_key: [BookMove, ...]} map for
        walking a game in one pass."""
        rows = self.session.execute(
            select(RepertoireMove).where(RepertoireMove.repertoire_id == repertoire_id)
        ).scalars().all()
        book: dict[str, list[BookMove]] = defaultdict(list)
        for r in rows:
            book[r.position_key].append(BookMove(r.move_uci, r.move_san, r.comment))
        return dict(book)


def find_deviations(
    book: dict[str, list[BookMove]],
    game_uci_moves: list[str],
    player_color: chess.Color,
) -> list[Deviation]:
    """Walk a game and return every ply where, on the player's own turn, the position
    is covered by the repertoire but the move played is not one of its book moves.

    Opponent moves are never flagged: once the opponent leaves the prepared line the
    resulting positions simply aren't in the book, so the walk stops finding matches
    naturally."""
    board = chess.Board()
    deviations: list[Deviation] = []
    for index, uci in enumerate(game_uci_moves):
        move = chess.Move.from_uci(uci)
        ply = index + 1
        position_key = position_key_from_fen(board.fen())
        expected = book.get(position_key)

        if board.turn == player_color and expected:
            book_ucis = {bm.move_uci for bm in expected}
            if uci not in book_ucis:
                deviations.append(
                    Deviation(
                        ply=ply,
                        position_key=position_key,
                        played_uci=uci,
                        played_san=board.san(move),
                        expected=list(expected),
                    )
                )
        board.push(move)
    return deviations
