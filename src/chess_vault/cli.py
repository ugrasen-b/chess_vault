from __future__ import annotations

import argparse

from chess_vault.analysis.analyze_service import AnalysisService, is_mate_score
from chess_vault.analysis.features import build_player_report
from chess_vault.db.session import init_db, make_session_factory
from chess_vault.ingest.sync_service import SyncService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="chess-vault")
    subparsers = parser.add_subparsers(dest="command", required=True)

    sync_parser = subparsers.add_parser("sync", help="Sync games from connected providers")
    sync_parser.add_argument("--lichess", type=str, default=None, help="Lichess username")
    sync_parser.add_argument("--chesscom", type=str, default=None, help="Chess.com username")
    sync_parser.add_argument("--max-games", type=int, default=50, help="Max Lichess games to fetch")
    sync_parser.add_argument(
        "--max-months",
        type=int,
        default=3,
        help="How many recent monthly archives to fetch from Chess.com",
    )

    report_parser = subparsers.add_parser("report", help="Show aggregated stats for a player")
    report_parser.add_argument("--player", required=True, type=str, help="Player username")
    report_parser.add_argument("--top", type=int, default=5, help="Top N lines to show")
    report_parser.add_argument(
        "--min-family-games",
        type=int,
        default=5,
        help="Minimum games required for opening-family win-rate rows",
    )

    analyze_parser = subparsers.add_parser("analyze", help="Run engine analysis and detect mistakes")
    analyze_parser.add_argument("--player", required=True, type=str, help="Player username")
    analyze_parser.add_argument("--source", choices=["lichess", "chesscom"], default=None)
    analyze_parser.add_argument("--max-games", type=int, default=50)
    analyze_parser.add_argument("--engine-path", type=str, default="stockfish")
    analyze_parser.add_argument("--depth", type=int, default=12)
    analyze_parser.add_argument("--win-threshold", type=int, default=200)
    analyze_parser.add_argument("--drop-to", type=int, default=0)
    analyze_parser.add_argument("--lookahead-plies", type=int, default=3)

    mistakes_parser = subparsers.add_parser("mistakes", help="List persisted mistakes")
    mistakes_parser.add_argument("--player", required=True, type=str, help="Player username")
    mistakes_parser.add_argument("--type", default="thrown_advantage", type=str, help="Mistake category")
    mistakes_parser.add_argument("--limit", default=20, type=int)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    init_db()
    session_factory = make_session_factory()

    if args.command == "sync":
        if not args.lichess and not args.chesscom:
            parser.error("Provide at least one source: --lichess and/or --chesscom")

        with session_factory() as session:
            service = SyncService(session)

            if args.lichess:
                result = service.sync_lichess(username=args.lichess, max_games=args.max_games)
                print(
                    f"[lichess] fetched={result.fetched} inserted={result.inserted} "
                    f"skipped={result.skipped_existing}"
                )

            if args.chesscom:
                result = service.sync_chesscom(username=args.chesscom, max_months=args.max_months)
                print(
                    f"[chesscom] fetched={result.fetched} inserted={result.inserted} "
                    f"skipped={result.skipped_existing}"
                )
        return

    if args.command == "report":
        with session_factory() as session:
            report = build_player_report(
                session=session,
                player=args.player,
                top_n=max(1, args.top),
                min_family_games=max(1, args.min_family_games),
            )
            print(f"player={report.player}")
            print(f"games={report.total_games} w={report.wins} l={report.losses} d={report.draws}")

            print("by_source:")
            for source, count in report.by_source:
                print(f"  - {source}: {count}")

            print("top_openings_played:")
            for opening, count in report.top_openings_played:
                print(f"  - {opening}: {count}")

            print("top_opponent_openings_against_you:")
            for opening, count in report.top_opponent_openings_against_you:
                print(f"  - {opening}: {count}")

            print("top_opening_families_played:")
            for family, count in report.top_opening_families_played:
                print(f"  - {family}: {count}")

            print("opening_family_performance:")
            for row in report.opening_family_performance:
                print(
                    f"  - {row.family}: games={row.games} "
                    f"w={row.wins} l={row.losses} d={row.draws} winrate={row.win_rate:.1f}%"
                )
        return

    if args.command == "analyze":
        with session_factory() as session:
            service = AnalysisService(session)
            summary = service.analyze_player_games(
                player=args.player,
                source=args.source,
                max_games=max(1, args.max_games),
                engine_path=args.engine_path,
                depth=max(1, args.depth),
                win_threshold_cp=args.win_threshold,
                drop_to_cp=args.drop_to,
                lookahead_plies=max(1, args.lookahead_plies),
            )
            print(
                f"analysis_run={summary.analysis_run_id} "
                f"games_scanned={summary.games_scanned} mistakes_found={summary.mistakes_found}"
            )
        return

    if args.command == "mistakes":
        with session_factory() as session:
            service = AnalysisService(session)
            rows = service.list_mistakes(
                player=args.player,
                category=args.type,
                limit=max(1, args.limit),
                latest_run_only=True,
                dedupe_by_game=True,
            )
            print(f"mistakes={len(rows)}")
            for row in rows:
                mate_swing = is_mate_score(row.before_eval_cp) or is_mate_score(row.after_eval_cp)
                print(
                    f"  - game_id={row.game_id} ply={row.ply} move={row.move_uci} "
                    f"before={row.before_eval_cp} after={row.after_eval_cp} "
                    f"swing={row.swing_cp} mate_swing={'yes' if mate_swing else 'no'}"
                )
        return

    parser.error("Unknown command")


if __name__ == "__main__":
    main()
