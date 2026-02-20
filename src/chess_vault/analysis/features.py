from __future__ import annotations

from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from chess_vault.db.models import Game


def opening_frequency(session: Session) -> list[tuple[str, int]]:
    rows = session.execute(select(Game.opening)).scalars().all()
    counts = Counter([r for r in rows if r])
    return counts.most_common()
