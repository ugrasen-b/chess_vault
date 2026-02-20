from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Pitfall:
    key: str
    description: str
    count: int


def detect_pitfalls() -> list[Pitfall]:
    return []
