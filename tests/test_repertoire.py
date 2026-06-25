from __future__ import annotations

import chess
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from chess_vault.analysis.repertoire import (
    RepertoireService,
    find_deviations,
    san_line_to_uci,
)
from chess_vault.db.models import Base


def _make_session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def test_add_line_is_idempotent_and_updates_comment() -> None:
    Session = _make_session_factory()
    with Session() as session:
        service = RepertoireService(session)
        rep = service.create_repertoire("White e4", side="white")

        line = san_line_to_uci(["e4", "e5", "Nf3"])
        inserted = service.add_line(rep.id, line, comment_by_index={2: "develop knight"})
        assert inserted == 3

        # Re-saving the same line adds no new nodes.
        service.add_line(rep.id, line)
        book = service.load_book(rep.id)
        total_nodes = sum(len(v) for v in book.values())
        assert total_nodes == 3

        # Comment survived and is attached to the Nf3 node.
        nf3_key_board = chess.Board()
        nf3_key_board.push_san("e4")
        nf3_key_board.push_san("e5")
        from chess_vault.analysis.explorer import position_key_from_fen

        nf3_moves = service.book_moves_at(rep.id, position_key_from_fen(nf3_key_board.fen()))
        assert len(nf3_moves) == 1
        assert nf3_moves[0].move_san == "Nf3"
        assert nf3_moves[0].comment == "develop knight"


def test_add_line_supports_branching_alternatives() -> None:
    Session = _make_session_factory()
    with Session() as session:
        service = RepertoireService(session)
        rep = service.create_repertoire("Black vs e4", side="black")

        # Two prepared replies to 1.e4: ...c5 and ...e5.
        service.add_line(rep.id, san_line_to_uci(["e4", "c5"]))
        service.add_line(rep.id, san_line_to_uci(["e4", "e5"]))

        from chess_vault.analysis.explorer import position_key_from_fen

        after_e4 = chess.Board()
        after_e4.push_san("e4")
        replies = service.book_moves_at(rep.id, position_key_from_fen(after_e4.fen()))
        assert {m.move_san for m in replies} == {"c5", "e5"}


def test_find_deviations_flags_only_player_turn_off_book() -> None:
    Session = _make_session_factory()
    with Session() as session:
        service = RepertoireService(session)
        rep = service.create_repertoire("White e4", side="white")
        # Repertoire: 1.e4 e5 2.Nf3.
        service.add_line(
            rep.id, san_line_to_uci(["e4", "e5", "Nf3"]), comment_by_index={2: "main line"}
        )
        book = service.load_book(rep.id)

    # Game where the player (White) deviates at move 2 with Bc4 instead of Nf3.
    game = san_line_to_uci(["e4", "e5", "Bc4"])
    deviations = find_deviations(book, game, player_color=chess.WHITE)

    assert len(deviations) == 1
    dev = deviations[0]
    assert dev.ply == 3
    assert dev.played_san == "Bc4"
    assert {bm.move_san for bm in dev.expected} == {"Nf3"}
    assert dev.expected[0].comment == "main line"


def test_find_deviations_ignores_opponent_off_book_moves() -> None:
    Session = _make_session_factory()
    with Session() as session:
        service = RepertoireService(session)
        rep = service.create_repertoire("White e4", side="white")
        service.add_line(rep.id, san_line_to_uci(["e4", "e5", "Nf3"]))
        book = service.load_book(rep.id)

    # Opponent (Black) plays c5 instead of the prepared e5 — not the player's mistake.
    game = san_line_to_uci(["e4", "c5"])
    deviations = find_deviations(book, game, player_color=chess.WHITE)
    assert deviations == []


def test_find_deviations_no_match_when_following_book() -> None:
    Session = _make_session_factory()
    with Session() as session:
        service = RepertoireService(session)
        rep = service.create_repertoire("White e4", side="white")
        service.add_line(rep.id, san_line_to_uci(["e4", "e5", "Nf3"]))
        book = service.load_book(rep.id)

    game = san_line_to_uci(["e4", "e5", "Nf3", "Nc6"])
    deviations = find_deviations(book, game, player_color=chess.WHITE)
    assert deviations == []
