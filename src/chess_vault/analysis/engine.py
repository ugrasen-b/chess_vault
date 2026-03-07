from __future__ import annotations

from dataclasses import dataclass

import chess
import chess.engine


@dataclass(frozen=True)
class EvalResult:
    score_cp: int
    best_move_uci: str | None
    pv: str | None


class StockfishAnalyzer:
    def __init__(self, engine_path: str = "stockfish", depth: int = 12) -> None:
        self.engine_path = engine_path
        self.depth = depth
        self._engine: chess.engine.SimpleEngine | None = None
        self.engine_name = "stockfish"
        self.engine_version: str | None = None

    def __enter__(self) -> StockfishAnalyzer:
        self._engine = chess.engine.SimpleEngine.popen_uci(self.engine_path)
        engine_id = getattr(self._engine, "id", {}) or {}
        self.engine_name = engine_id.get("name", "stockfish")
        self.engine_version = engine_id.get("author")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._engine is not None:
            self._engine.quit()
            self._engine = None

    def evaluate_fen(self, fen: str, player_color: chess.Color) -> EvalResult:
        if self._engine is None:
            raise RuntimeError("StockfishAnalyzer must be used as a context manager.")

        board = chess.Board(fen=fen)
        info = self._engine.analyse(board, chess.engine.Limit(depth=self.depth))
        pov = info["score"].pov(player_color)
        score_cp = pov.score(mate_score=100_000)
        if score_cp is None:
            score_cp = 0

        pv_moves = info.get("pv", [])
        best_move_uci = pv_moves[0].uci() if pv_moves else None
        pv = " ".join(move.uci() for move in pv_moves[:8]) if pv_moves else None
        return EvalResult(score_cp=score_cp, best_move_uci=best_move_uci, pv=pv)
