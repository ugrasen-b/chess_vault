from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from chess_vault.analysis.explorer import (
    PositionIndexService,
    lookup_position,
    position_key_from_fen,
)
from chess_vault.db.models import Base, Game, PositionOccurrence

GAME_E4_E5_NF3 = """
[Event "Test"]
[Site "https://example.com/game/1"]
[White "hero"]
[Black "opp1"]
[Result "1-0"]

1. e4 e5 2. Nf3 Nc6 1-0
""".strip()

GAME_E4_C5 = """
[Event "Test"]
[Site "https://example.com/game/2"]
[White "hero"]
[Black "opp2"]
[Result "0-1"]

1. e4 c5 0-1
""".strip()

GAME_D4 = """
[Event "Test"]
[Site "https://example.com/game/3"]
[White "opp3"]
[Black "hero"]
[Result "1/2-1/2"]

1. d4 d5 1/2-1/2
""".strip()

GAME_ABANDONED_NO_MOVES = """
[Event "Test"]
[Site "https://example.com/game/4"]
[White "hero"]
[Black "opp4"]
[Result "0-1"]
[Termination "Abandoned"]

0-1
""".strip()


def _make_session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def test_position_key_from_fen_strips_clocks() -> None:
    full_fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    assert position_key_from_fen(full_fen) == "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -"

    later_fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 4 12"
    assert position_key_from_fen(later_fen) == position_key_from_fen(full_fen)


def test_index_unindexed_games_is_idempotent() -> None:
    Session = _make_session_factory()
    with Session() as session:
        session.add(
            Game(source="chesscom", source_game_id="g1", white_player="hero", black_player="opp1",
                 result="1-0", raw_pgn=GAME_E4_E5_NF3)
        )
        session.commit()

        service = PositionIndexService(session)
        first_run = service.index_unindexed_games()
        assert first_run.games_indexed == 1
        assert first_run.occurrences_inserted == 4  # e4, e5, Nf3, Nc6

        second_run = service.index_unindexed_games()
        assert second_run.games_indexed == 0
        assert second_run.occurrences_inserted == 0

        rows = session.execute(select(PositionOccurrence)).scalars().all()
        assert len(rows) == 4
        first_move = next(row for row in rows if row.ply == 1)
        assert first_move.turn == "w"
        assert first_move.move_uci == "e2e4"
        assert first_move.move_san == "e4"


def test_lookup_position_aggregates_next_moves_and_results() -> None:
    Session = _make_session_factory()
    with Session() as session:
        session.add_all(
            [
                Game(source="chesscom", source_game_id="g1", white_player="hero", black_player="opp1",
                     result="1-0", raw_pgn=GAME_E4_E5_NF3),
                Game(source="chesscom", source_game_id="g2", white_player="hero", black_player="opp2",
                     result="0-1", raw_pgn=GAME_E4_C5),
                Game(source="lichess", source_game_id="g3", white_player="opp3", black_player="hero",
                     result="1/2-1/2", raw_pgn=GAME_D4),
            ]
        )
        session.commit()

        PositionIndexService(session).index_unindexed_games()

        stats = lookup_position(session=session, player="hero", moves=[])

    assert stats.total_games == 3
    assert stats.white_wins == 1
    assert stats.black_wins == 1
    assert stats.draws == 1
    by_san = {move.move_san: move for move in stats.next_moves}
    assert by_san["e4"].games == 2
    assert by_san["e4"].white_wins == 1
    assert by_san["e4"].black_wins == 1
    assert by_san["d4"].games == 1
    assert by_san["d4"].draws == 1


def test_index_unindexed_games_does_not_rescan_zero_move_games() -> None:
    Session = _make_session_factory()
    with Session() as session:
        session.add(
            Game(source="lichess", source_game_id="g1", white_player="hero", black_player="opp4",
                 result="0-1", raw_pgn=GAME_ABANDONED_NO_MOVES)
        )
        session.commit()

        service = PositionIndexService(session)
        first_run = service.index_unindexed_games()
        assert first_run.games_indexed == 1
        assert first_run.occurrences_inserted == 0

        second_run = service.index_unindexed_games()
        assert second_run.games_indexed == 0


def test_lookup_position_scopes_deeper_position_to_player_games() -> None:
    Session = _make_session_factory()
    with Session() as session:
        session.add_all(
            [
                Game(source="chesscom", source_game_id="g1", white_player="hero", black_player="opp1",
                     result="1-0", raw_pgn=GAME_E4_E5_NF3),
                Game(source="chesscom", source_game_id="g2", white_player="hero", black_player="opp2",
                     result="0-1", raw_pgn=GAME_E4_C5),
            ]
        )
        session.commit()

        PositionIndexService(session).index_unindexed_games()

        stats = lookup_position(session=session, player="hero", moves=["e4"])

    assert stats.total_games == 2
    by_san = {move.move_san: move for move in stats.next_moves}
    assert by_san["e5"].games == 1
    assert by_san["c5"].games == 1


def test_lookup_position_perspective_filters_by_player_color() -> None:
    Session = _make_session_factory()
    with Session() as session:
        session.add_all(
            [
                Game(source="chesscom", source_game_id="g1", white_player="hero", black_player="opp1",
                     result="1-0", raw_pgn=GAME_E4_E5_NF3),
                Game(source="chesscom", source_game_id="g2", white_player="hero", black_player="opp2",
                     result="0-1", raw_pgn=GAME_E4_C5),
                Game(source="lichess", source_game_id="g3", white_player="opp3", black_player="hero",
                     result="1/2-1/2", raw_pgn=GAME_D4),
            ]
        )
        session.commit()

        PositionIndexService(session).index_unindexed_games()

        white_stats = lookup_position(session=session, player="hero", moves=[], perspective="white")
        black_stats = lookup_position(session=session, player="hero", moves=[], perspective="black")

    assert white_stats.total_games == 2
    assert {move.move_san for move in white_stats.next_moves} == {"e4"}

    assert black_stats.total_games == 1
    assert {move.move_san for move in black_stats.next_moves} == {"d4"}
