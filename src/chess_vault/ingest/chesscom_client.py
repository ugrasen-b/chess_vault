from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

import httpx

CHESSCOM_API_BASE = "https://api.chess.com/pub"


def _select_archives(archives: list[str], max_months: int | None) -> list[str]:
    ordered = list(reversed(archives))
    # Chess.com's archive list already spans the account's full history; a falsy
    # max_months means "fetch every month" instead of capping to the most recent N.
    if max_months is None or max_months <= 0:
        return ordered
    return ordered[:max_months]


class ChessComClient:
    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout = timeout

    def fetch_recent_games_pgn(
        self,
        username: str,
        max_months: int | None = 3,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> list[str]:
        normalized_username = username.strip().lower()
        archives = self._fetch_archives(username=normalized_username)
        if not archives:
            return []

        selected = _select_archives(archives, max_months)
        games: list[str] = []

        with httpx.Client(timeout=self.timeout) as client:
            for index, archive_url in enumerate(selected, start=1):
                response = client.get(archive_url)
                response.raise_for_status()
                payload = response.json()
                for game in payload.get("games", []):
                    pgn = game.get("pgn")
                    if pgn:
                        games.append(pgn)
                if on_progress:
                    on_progress(index, len(selected))

        return games

    def _fetch_archives(self, username: str) -> list[str]:
        url = f"{CHESSCOM_API_BASE}/player/{username}/games/archives"
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            response = client.get(url)
            if response.status_code == 404:
                return []
            response.raise_for_status()
            payload = response.json()

        return payload.get("archives", [])


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
