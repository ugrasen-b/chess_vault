from __future__ import annotations

import argparse

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
            report = build_player_report(session=session, player=args.player, top_n=max(1, args.top))
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
        return

    parser.error("Unknown command")


if __name__ == "__main__":
    main()
