from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    db_url: str = "sqlite:///./data/chess_vault.db"
    lichess_token: str | None = None


def get_settings() -> Settings:
    return Settings(
        db_url=os.getenv("CHESS_VAULT_DB_URL", "sqlite:///./data/chess_vault.db"),
        lichess_token=os.getenv("LICHESS_TOKEN") or None,
    )
