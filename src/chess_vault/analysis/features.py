from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from chess_vault.db.models import Game


@dataclass(frozen=True)
class OpeningFamilyPerformance:
    family: str
    games: int
    wins: int
    losses: int
    draws: int
    win_rate: float


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
    top_opening_families_played: list[tuple[str, int]]
    opening_family_performance: list[OpeningFamilyPerformance]


def _sorted_counts(counter: Counter[str], top_n: int | None = None) -> list[tuple[str, int]]:
    items = sorted(counter.items(), key=lambda item: (-item[1], item[0].lower()))
    if top_n is None:
        return items
    return items[:top_n]


def _normalize_opening_family(opening: str | None) -> str:
    if not opening:
        return "(Unknown)"

    value = opening.strip()
    lower = value.lower()
    family_by_match = [
        ("Caro-Kann Defense", ["caro kann", "caro-kann"]),
        ("Sicilian Defense", ["sicilian"]),
        ("French Defense", ["french defense", "french"]),
        ("Scandinavian Defense", ["scandinavian"]),
        ("Pirc Defense", ["pirc"]),
        ("Alekhine Defense", ["alekhine"]),
        ("King's Indian Defense", ["king's indian"]),
        ("Queen's Indian Defense", ["queen's indian"]),
        ("Nimzo-Indian Defense", ["nimzo", "nimzo-indian"]),
        ("Dutch Defense", ["dutch defense", "dutch"]),
        ("Grunfeld Defense", ["grunfeld", "grunfeld defense"]),
        ("Benoni Defense", ["benoni"]),
        ("Queen's Gambit", ["queen's gambit"]),
        ("King's Gambit", ["king's gambit"]),
        ("Ruy Lopez", ["ruy lopez", "spanish game"]),
        ("Italian Game", ["italian game", "giuoco piano", "evans gambit"]),
        ("Scotch Game", ["scotch game"]),
        ("Vienna Game", ["vienna"]),
        ("Four Knights Game", ["four knights"]),
        ("English Opening", ["english opening"]),
        ("Reti Opening", ["reti opening", "reti"]),
        ("London System", ["london system", "london"]),
        ("Catalan Opening", ["catalan"]),
        ("Bird Opening", ["bird opening", "bird"]),
    ]
    for family, needles in family_by_match:
        if any(needle in lower for needle in needles):
            return family

    # Fallback bucket keeps the first segment to avoid over-fragmented full strings.
    first_segment = value.split(":", maxsplit=1)[0].strip()
    if first_segment:
        return first_segment
    return value


def opening_frequency(session: Session) -> list[tuple[str, int]]:
    rows = session.execute(select(Game.opening)).scalars().all()
    counts = Counter([r for r in rows if r])
    return _sorted_counts(counts)


def build_player_report(
    session: Session,
    player: str,
    top_n: int = 5,
    min_family_games: int = 5,
) -> PlayerReport:
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
    family_counter: Counter[str] = Counter()
    family_record: dict[str, dict[str, int]] = {}

    for game in games:
        white = (game.white_player or "").lower()
        black = (game.black_player or "").lower()
        result = game.result
        opening = game.opening or "(Unknown)"
        family = _normalize_opening_family(opening)

        by_source_counter[game.source] += 1
        openings_played_counter[opening] += 1
        family_counter[family] += 1

        if family not in family_record:
            family_record[family] = {"games": 0, "wins": 0, "losses": 0, "draws": 0}
        family_record[family]["games"] += 1

        if black == norm_player:
            opponent_openings_counter[opening] += 1

        if result == "1/2-1/2":
            draws += 1
            family_record[family]["draws"] += 1
        elif result == "1-0":
            if white == norm_player:
                wins += 1
                family_record[family]["wins"] += 1
            elif black == norm_player:
                losses += 1
                family_record[family]["losses"] += 1
        elif result == "0-1":
            if black == norm_player:
                wins += 1
                family_record[family]["wins"] += 1
            elif white == norm_player:
                losses += 1
                family_record[family]["losses"] += 1

    performance_rows: list[OpeningFamilyPerformance] = []
    for family, record in family_record.items():
        games_count = record["games"]
        if games_count < min_family_games:
            continue
        wins_count = record["wins"]
        losses_count = record["losses"]
        draws_count = record["draws"]
        win_rate = (wins_count / games_count) * 100 if games_count else 0.0
        performance_rows.append(
            OpeningFamilyPerformance(
                family=family,
                games=games_count,
                wins=wins_count,
                losses=losses_count,
                draws=draws_count,
                win_rate=win_rate,
            )
        )
    performance_rows.sort(key=lambda row: (-row.games, -row.win_rate, row.family.lower()))

    return PlayerReport(
        player=player,
        total_games=len(games),
        wins=wins,
        losses=losses,
        draws=draws,
        by_source=_sorted_counts(by_source_counter),
        top_openings_played=_sorted_counts(openings_played_counter, top_n=top_n),
        top_opponent_openings_against_you=_sorted_counts(opponent_openings_counter, top_n=top_n),
        top_opening_families_played=_sorted_counts(family_counter, top_n=top_n),
        opening_family_performance=performance_rows[:top_n],
    )
