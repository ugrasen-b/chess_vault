from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import re

HEADER_RE = re.compile(r'^\[(?P<key>[^\s]+)\s+"(?P<value>.*)"\]$')


@dataclass(frozen=True)
class NormalizedGame:
    source_game_id: str
    source: str
    white_player: str | None
    black_player: str | None
    result: str | None
    time_control: str | None
    eco: str | None
    opening: str | None
    event: str | None
    site: str | None
    played_at: datetime | None
    raw_pgn: str


def normalize_pgn(source: str, raw_pgn: str) -> NormalizedGame:
    headers = _extract_headers(raw_pgn)
    source_game_id = _derive_source_game_id(headers=headers, raw_pgn=raw_pgn)
    return NormalizedGame(
        source_game_id=source_game_id,
        source=source,
        white_player=headers.get("White"),
        black_player=headers.get("Black"),
        result=headers.get("Result"),
        time_control=headers.get("TimeControl"),
        eco=headers.get("ECO"),
        opening=headers.get("Opening"),
        event=headers.get("Event"),
        site=headers.get("Site"),
        played_at=_parse_date(headers.get("UTCDate"), headers.get("UTCTime"), headers.get("Date")),
        raw_pgn=raw_pgn,
    )


def _extract_headers(raw_pgn: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in raw_pgn.splitlines():
        line = line.strip()
        if not line.startswith("["):
            break
        match = HEADER_RE.match(line)
        if match:
            out[match.group("key")] = match.group("value")
    return out


def _derive_source_game_id(headers: dict[str, str], raw_pgn: str) -> str:
    site = headers.get("Site")
    if site:
        site_value = site.strip()
        # Some providers (notably Chess.com) can emit a non-unique literal Site tag like "Chess.com".
        # Only trust Site as an ID when it appears URL-like.
        if site_value.startswith("http://") or site_value.startswith("https://"):
            return site_value
    digest = hashlib.sha256(raw_pgn.encode("utf-8")).hexdigest()
    return digest


def _parse_date(utc_date: str | None, utc_time: str | None, date: str | None) -> datetime | None:
    if utc_date and utc_time:
        try:
            return datetime.strptime(f"{utc_date} {utc_time}", "%Y.%m.%d %H:%M:%S")
        except ValueError:
            pass

    if date and date != "????.??.??":
        try:
            return datetime.strptime(date, "%Y.%m.%d")
        except ValueError:
            return None

    return None
