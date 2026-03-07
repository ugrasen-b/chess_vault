from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from io import StringIO

import chess
import chess.pgn
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from chess_vault.analysis.engine import StockfishAnalyzer
from chess_vault.db.models import AnalysisRun, EngineEval, Game, GameMistake


@dataclass(frozen=True)
class PositionBoundary:
    boundary_index: int
    ply: int
    fen: str
    turn: chess.Color
    move_uci: str | None


@dataclass(frozen=True)
class ThrownAdvantageCandidate:
    ply: int
    fen: str
    move_uci: str
    before_eval_cp: int
    after_eval_cp: int
    swing_cp: int


@dataclass(frozen=True)
class AnalyzeSummary:
    analysis_run_id: int
    games_scanned: int
    mistakes_found: int


def extract_position_boundaries(raw_pgn: str) -> list[PositionBoundary]:
    game = chess.pgn.read_game(StringIO(raw_pgn))
    if game is None:
        return []

    board = game.board()
    boundaries: list[PositionBoundary] = [
        PositionBoundary(boundary_index=0, ply=1, fen=board.fen(), turn=board.turn, move_uci=None)
    ]
    ply = 1
    for move in game.mainline_moves():
        board.push(move)
        boundaries.append(
            PositionBoundary(
                boundary_index=ply,
                ply=ply + 1,
                fen=board.fen(),
                turn=board.turn,
                move_uci=move.uci(),
            )
        )
        ply += 1
    return boundaries


def detect_thrown_advantage(
    boundaries: list[PositionBoundary],
    eval_cp_by_boundary: dict[int, int],
    player_color: chess.Color,
    win_threshold_cp: int = 200,
    drop_to_cp: int = 0,
    lookahead_plies: int = 3,
) -> list[ThrownAdvantageCandidate]:
    findings: list[ThrownAdvantageCandidate] = []
    last_index = len(boundaries) - 1

    for idx in range(last_index):
        boundary = boundaries[idx]
        if boundary.turn != player_color:
            continue
        before_cp = eval_cp_by_boundary.get(idx, 0)
        if before_cp < win_threshold_cp:
            continue

        move_uci = boundaries[idx + 1].move_uci
        if not move_uci:
            continue

        worst_after = before_cp
        for ahead in range(1, lookahead_plies + 1):
            probe_idx = min(idx + ahead, last_index)
            after_cp = eval_cp_by_boundary.get(probe_idx, 0)
            if after_cp < worst_after:
                worst_after = after_cp

        if worst_after <= drop_to_cp:
            findings.append(
                ThrownAdvantageCandidate(
                    ply=idx + 1,
                    fen=boundary.fen,
                    move_uci=move_uci,
                    before_eval_cp=before_cp,
                    after_eval_cp=worst_after,
                    swing_cp=before_cp - worst_after,
                )
            )
    return findings


class AnalysisService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def analyze_player_games(
        self,
        player: str,
        source: str | None,
        max_games: int,
        engine_path: str,
        depth: int,
        win_threshold_cp: int,
        drop_to_cp: int,
        lookahead_plies: int,
    ) -> AnalyzeSummary:
        norm_player = player.strip().lower()
        player_filter = or_(
            func.lower(Game.white_player) == norm_player,
            func.lower(Game.black_player) == norm_player,
        )
        stmt = select(Game).where(player_filter)
        if source:
            stmt = stmt.where(Game.source == source)
        stmt = stmt.order_by(desc(Game.played_at)).limit(max_games)
        games = self.session.execute(stmt).scalars().all()

        with StockfishAnalyzer(engine_path=engine_path, depth=depth) as analyzer:
            run = AnalysisRun(
                player=player,
                source=source,
                status="running",
                engine_name=analyzer.engine_name,
                engine_version=analyzer.engine_version or "unknown",
                depth=depth,
                win_threshold_cp=win_threshold_cp,
                drop_to_cp=drop_to_cp,
                lookahead_plies=lookahead_plies,
            )
            self.session.add(run)
            self.session.flush()

            total_mistakes = 0
            for game in games:
                color = self._player_color(game=game, player=norm_player)
                if color is None:
                    continue

                boundaries = extract_position_boundaries(game.raw_pgn)
                if len(boundaries) < 2:
                    continue

                eval_map: dict[int, int] = {}
                for boundary in boundaries:
                    eval_map[boundary.boundary_index] = self._get_or_create_eval(
                        fen=boundary.fen,
                        depth=depth,
                        engine_name=analyzer.engine_name,
                        engine_version=analyzer.engine_version or "unknown",
                        player_color=color,
                        analyzer=analyzer,
                    )

                findings = detect_thrown_advantage(
                    boundaries=boundaries,
                    eval_cp_by_boundary=eval_map,
                    player_color=color,
                    win_threshold_cp=win_threshold_cp,
                    drop_to_cp=drop_to_cp,
                    lookahead_plies=lookahead_plies,
                )
                for finding in findings:
                    self.session.add(
                        GameMistake(
                            analysis_run_id=run.id,
                            game_id=game.id,
                            player=player,
                            category="thrown_advantage",
                            ply=finding.ply,
                            fen=finding.fen,
                            move_uci=finding.move_uci,
                            before_eval_cp=finding.before_eval_cp,
                            after_eval_cp=finding.after_eval_cp,
                            swing_cp=finding.swing_cp,
                        )
                    )
                total_mistakes += len(findings)

            run.games_scanned = len(games)
            run.mistakes_found = total_mistakes
            run.status = "completed"
            run.completed_at = datetime.utcnow()
            self.session.commit()
            return AnalyzeSummary(
                analysis_run_id=run.id,
                games_scanned=run.games_scanned,
                mistakes_found=run.mistakes_found,
            )

    def list_mistakes(
        self,
        player: str,
        category: str = "thrown_advantage",
        limit: int = 20,
    ) -> list[GameMistake]:
        stmt = (
            select(GameMistake)
            .where(
                func.lower(GameMistake.player) == player.strip().lower(),
                GameMistake.category == category,
            )
            .order_by(desc(GameMistake.swing_cp))
            .limit(limit)
        )
        return self.session.execute(stmt).scalars().all()

    def _get_or_create_eval(
        self,
        fen: str,
        depth: int,
        engine_name: str,
        engine_version: str,
        player_color: chess.Color,
        analyzer: StockfishAnalyzer,
    ) -> int:
        existing = self.session.execute(
            select(EngineEval).where(
                EngineEval.fen == fen,
                EngineEval.depth == depth,
                EngineEval.engine_name == engine_name,
                EngineEval.engine_version == engine_version,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing.score_cp

        result = analyzer.evaluate_fen(fen=fen, player_color=player_color)
        row = EngineEval(
            fen=fen,
            depth=depth,
            engine_name=engine_name,
            engine_version=engine_version,
            score_cp=result.score_cp,
            best_move_uci=result.best_move_uci,
            pv=result.pv,
        )
        self.session.add(row)
        self.session.flush()
        return row.score_cp

    @staticmethod
    def _player_color(game: Game, player: str) -> chess.Color | None:
        white = (game.white_player or "").lower()
        black = (game.black_player or "").lower()
        if white == player:
            return chess.WHITE
        if black == player:
            return chess.BLACK
        return None
