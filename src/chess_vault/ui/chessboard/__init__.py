from __future__ import annotations

from pathlib import Path

import chess
import streamlit.components.v1 as components

_BUILD_DIR = Path(__file__).parent / "static"
_component_func = components.declare_component("chess_vault_chessboard", path=str(_BUILD_DIR))


def legal_dests(board: chess.Board) -> dict[str, list[str]]:
    dests: dict[str, list[str]] = {}
    for move in board.legal_moves:
        orig = chess.square_name(move.from_square)
        dest = chess.square_name(move.to_square)
        dests.setdefault(orig, [])
        if dest not in dests[orig]:
            dests[orig].append(dest)
    return dests


def chessboard(
    fen: str,
    orientation: str = "white",
    dests: dict[str, list[str]] | None = None,
    last_move: tuple[str, str] | None = None,
    size: int = 480,
    key: str | None = None,
) -> dict[str, str] | None:
    """Renders an interactive chessground board. Returns {"orig": ..., "dest": ...}
    when the user makes a move, else None."""
    return _component_func(
        fen=fen,
        orientation=orientation,
        dests=dests or {},
        lastMove=list(last_move) if last_move else None,
        size=size,
        key=key,
        default=None,
    )
