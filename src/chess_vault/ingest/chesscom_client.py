from __future__ import annotations

from datetime import datetime, timezone

import httpx

CHESSCOM_API_BASE = "https://api.chess.com/pub"


class ChessComClient:
    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout = timeout

    def fetch_recent_games_pgn(self, username: str, max_months: int = 3) -> list[str]:
        normalized_username = username.strip().lower()
        archives = self._fetch_archives(username=normalized_username)
        if not archives:
            return []

        selected = list(reversed(archives))[:max_months]
        games: list[str] = []

        with httpx.Client(timeout=self.timeout) as client:
            for archive_url in selected:
                response = client.get(archive_url)
                response.raise_for_status()
                payload = response.json()
                for game in payload.get("games", []):
                    pgn = game.get("pgn")
                    if pgn:
                        games.append(pgn)

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
