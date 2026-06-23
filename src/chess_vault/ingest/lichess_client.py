from __future__ import annotations

import re
from collections.abc import Callable, Iterable

import httpx

from chess_vault.config import get_settings

LICHESS_API_BASE = "https://lichess.org/api"


def _build_request_params(max_games: int | None) -> dict[str, object]:
    params: dict[str, object] = {"moves": True, "clocks": False, "evals": False, "opening": True}
    # Lichess: omitting "max" downloads the user's full game history instead of a page of it.
    if max_games is not None and max_games > 0:
        params["max"] = max_games
    return params


class LichessClient:
    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout = timeout
        self.settings = get_settings()

    def fetch_user_games_pgn(
        self,
        username: str,
        max_games: int | None = 50,
        on_progress: Callable[[int], None] | None = None,
    ) -> list[str]:
        headers = {"Accept": "application/x-chess-pgn"}
        if self.settings.lichess_token:
            headers["Authorization"] = f"Bearer {self.settings.lichess_token}"

        params = _build_request_params(max_games)
        url = f"{LICHESS_API_BASE}/games/user/{username}"

        # A full-history export can run for many minutes; only the connect phase needs a
        # tight timeout, the read phase must stay open for as long as Lichess keeps streaming.
        timeout = httpx.Timeout(
            connect=self.timeout, read=None, write=self.timeout, pool=self.timeout
        )

        games: list[str] = []
        current: list[str] = []
        with httpx.Client(timeout=timeout) as client, client.stream(
            "GET", url, params=params, headers=headers
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line.startswith('[Event "') and current:
                    games.append("\n".join(current).strip())
                    if on_progress:
                        on_progress(len(games))
                    current = []
                if line.strip() or current:
                    current.append(line)

        if current:
            games.append("\n".join(current).strip())
            if on_progress:
                on_progress(len(games))

        return games


def _split_pgn_batch(payload: str) -> list[str]:
    # Lichess bulk PGN exports are separated by blank lines before next [Event ...] block.
    blocks = re.split(r"\n{2,}(?=\[Event\s+\")", payload.strip())
    return [b.strip() for b in blocks if b.strip()]


def iter_recent_games(username: str, max_games: int = 50) -> Iterable[str]:
    client = LichessClient()
    return client.fetch_user_games_pgn(username=username, max_games=max_games)
