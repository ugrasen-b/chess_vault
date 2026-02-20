from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from chess_vault.analysis.features import build_player_report
from chess_vault.db.models import Base, Game


def test_build_player_report_aggregates_stats() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    with Session() as session:
        session.add_all(
            [
                Game(
                    source="chesscom",
                    source_game_id="a",
                    white_player="OrwellFan",
                    black_player="alice",
                    result="1-0",
                    opening="Sicilian Defense",
                    raw_pgn="pgn-a",
                ),
                Game(
                    source="lichess",
                    source_game_id="b",
                    white_player="bob",
                    black_player="orwellfan",
                    result="1-0",
                    opening="Queen's Gambit",
                    raw_pgn="pgn-b",
                ),
                Game(
                    source="chesscom",
                    source_game_id="c",
                    white_player="ORWELLFAN",
                    black_player="carol",
                    result="1/2-1/2",
                    opening="Italian Game",
                    raw_pgn="pgn-c",
                ),
                Game(
                    source="lichess",
                    source_game_id="d",
                    white_player="dave",
                    black_player="eve",
                    result="0-1",
                    opening="French Defense",
                    raw_pgn="pgn-d",
                ),
            ]
        )
        session.commit()

        report = build_player_report(session=session, player="OrwellFan", top_n=2)

    assert report.total_games == 3
    assert report.wins == 1
    assert report.losses == 1
    assert report.draws == 1
    assert report.by_source == [("chesscom", 2), ("lichess", 1)]
    assert report.top_openings_played == [("Italian Game", 1), ("Queen's Gambit", 1)]
    assert report.top_opponent_openings_against_you == [("Queen's Gambit", 1)]
