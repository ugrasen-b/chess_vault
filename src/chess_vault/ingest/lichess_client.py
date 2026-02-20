from __future__ import annotations

from typing import Iterable

import httpx

from chess_vault.config import get_settings

LICHESS_API_BASE = "https://lichess.org/api"


class LichessClient:
    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout = timeout
        self.settings = get_settings()

    def fetch_user_games_pgn(self, username: str, max_games: int = 50) -> list[str]:
        headers = {"Accept": "application/x-ndjson"}
        if self.settings.lichess_token:
            headers["Authorization"] = f"Bearer {self.settings.lichess_token}"

        params = {
            "max": max_games,
            "pgnInJson": False,
            "moves": True,
            "clocks": False,
            "evals": False,
            "opening": True,
        }

        url = f"{LICHESS_API_BASE}/games/user/{username}"
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(url, params=params, headers=headers)
            response.raise_for_status()

        return _split_pgn_batch(response.text)


def _split_pgn_batch(payload: str) -> list[str]:
    blocks = payload.split("\n\n\n")
    return [b.strip() for b in blocks if b.strip()]


def iter_recent_games(username: str, max_games: int = 50) -> Iterable[str]:
    client = LichessClient()
    return client.fetch_user_games_pgn(username=username, max_games=max_games)
