from __future__ import annotations

import chess

from chess_vault.analysis.analyze_service import (
    PositionBoundary,
    detect_thrown_advantage,
    extract_position_boundaries,
    is_mate_score,
)


def test_extract_position_boundaries_reads_mainline() -> None:
    pgn = """
[Event "Test"]
[Site "https://example.com/game/1"]
[White "alice"]
[Black "bob"]
[Result "*"]

1. e4 e5 2. Nf3 Nc6 *
""".strip()
    boundaries = extract_position_boundaries(pgn)
    assert len(boundaries) == 5
    assert boundaries[0].move_uci is None
    assert boundaries[1].move_uci == "e2e4"


def test_detect_thrown_advantage_flags_drop() -> None:
    boundaries = [
        PositionBoundary(boundary_index=0, ply=1, fen="fen0", turn=chess.WHITE, move_uci=None),
        PositionBoundary(boundary_index=1, ply=2, fen="fen1", turn=chess.BLACK, move_uci="e2e4"),
        PositionBoundary(boundary_index=2, ply=3, fen="fen2", turn=chess.WHITE, move_uci="e7e5"),
        PositionBoundary(boundary_index=3, ply=4, fen="fen3", turn=chess.BLACK, move_uci="g1f3"),
    ]
    eval_map = {0: 280, 1: 250, 2: -20, 3: -10}
    findings = detect_thrown_advantage(
        boundaries=boundaries,
        eval_cp_by_boundary=eval_map,
        player_color=chess.WHITE,
        win_threshold_cp=200,
        drop_to_cp=0,
        lookahead_plies=3,
    )
    assert len(findings) == 1
    finding = findings[0]
    assert finding.ply == 1
    assert finding.move_uci == "e2e4"
    assert finding.before_eval_cp == 280
    assert finding.after_eval_cp == -20
    assert finding.swing_cp == 300


def test_is_mate_score_threshold() -> None:
    assert is_mate_score(100000)
    assert is_mate_score(-90000)
    assert not is_mate_score(89999)
