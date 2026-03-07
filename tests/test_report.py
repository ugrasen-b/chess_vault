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

        report = build_player_report(session=session, player="OrwellFan", top_n=2, min_family_games=1)

    assert report.total_games == 3
    assert report.wins == 1
    assert report.losses == 1
    assert report.draws == 1
    assert report.by_source == [("chesscom", 2), ("lichess", 1)]
    assert report.top_openings_played == [("Italian Game", 1), ("Queen's Gambit", 1)]
    assert report.top_opponent_openings_against_you == [("Queen's Gambit", 1)]
    assert report.top_opening_families_played == [("Italian Game", 1), ("Queen's Gambit", 1)]
    families = [row.family for row in report.opening_family_performance]
    assert "Italian Game" in families
    assert "Sicilian Defense" in families


def test_build_player_report_groups_opening_families() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    with Session() as session:
        session.add_all(
            [
                Game(
                    source="chesscom",
                    source_game_id="f1",
                    white_player="hero",
                    black_player="opp1",
                    result="1-0",
                    opening="Caro Kann Defense Main Line 4...Nf6",
                    raw_pgn="pgn-f1",
                ),
                Game(
                    source="chesscom",
                    source_game_id="f2",
                    white_player="opp2",
                    black_player="hero",
                    result="1-0",
                    opening="Caro Kann Defense Exchange Variation 3...cxd5 4.Nf3",
                    raw_pgn="pgn-f2",
                ),
                Game(
                    source="chesscom",
                    source_game_id="f3",
                    white_player="hero",
                    black_player="opp3",
                    result="1/2-1/2",
                    opening="Caro-Kann Defense",
                    raw_pgn="pgn-f3",
                ),
            ]
        )
        session.commit()

        report = build_player_report(session=session, player="hero", top_n=3, min_family_games=2)

    assert report.top_opening_families_played == [("Caro-Kann Defense", 3)]
    assert len(report.opening_family_performance) == 1
    family = report.opening_family_performance[0]
    assert family.family == "Caro-Kann Defense"
    assert family.games == 3
    assert family.wins == 1
    assert family.losses == 1
    assert family.draws == 1
