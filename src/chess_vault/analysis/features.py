from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from chess_vault.db.models import Game


@dataclass(frozen=True)
class PlayerReport:
    player: str
    total_games: int
    wins: int
    losses: int
    draws: int
    by_source: list[tuple[str, int]]
    top_openings_played: list[tuple[str, int]]
    top_opponent_openings_against_you: list[tuple[str, int]]


def _sorted_counts(counter: Counter[str], top_n: int | None = None) -> list[tuple[str, int]]:
    items = sorted(counter.items(), key=lambda item: (-item[1], item[0].lower()))
    if top_n is None:
        return items
    return items[:top_n]


def opening_frequency(session: Session) -> list[tuple[str, int]]:
    rows = session.execute(select(Game.opening)).scalars().all()
    counts = Counter([r for r in rows if r])
    return _sorted_counts(counts)


def build_player_report(session: Session, player: str, top_n: int = 5) -> PlayerReport:
    norm_player = player.strip().lower()

    games = session.execute(
        select(Game).where(
            or_(
                func.lower(Game.white_player) == norm_player,
                func.lower(Game.black_player) == norm_player,
            )
        )
    ).scalars().all()

    wins = 0
    losses = 0
    draws = 0
    by_source_counter: Counter[str] = Counter()
    openings_played_counter: Counter[str] = Counter()
    opponent_openings_counter: Counter[str] = Counter()

    for game in games:
        white = (game.white_player or "").lower()
        black = (game.black_player or "").lower()
        result = game.result
        opening = game.opening or "(Unknown)"

        by_source_counter[game.source] += 1
        openings_played_counter[opening] += 1

        if black == norm_player:
            opponent_openings_counter[opening] += 1

        if result == "1/2-1/2":
            draws += 1
        elif result == "1-0":
            if white == norm_player:
                wins += 1
            elif black == norm_player:
                losses += 1
        elif result == "0-1":
            if black == norm_player:
                wins += 1
            elif white == norm_player:
                losses += 1

    return PlayerReport(
        player=player,
        total_games=len(games),
        wins=wins,
        losses=losses,
        draws=draws,
        by_source=_sorted_counts(by_source_counter),
        top_openings_played=_sorted_counts(openings_played_counter, top_n=top_n),
        top_opponent_openings_against_you=_sorted_counts(opponent_openings_counter, top_n=top_n),
    )
