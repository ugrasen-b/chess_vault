from __future__ import annotations

import argparse

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

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command != "sync":
        parser.error("Unknown command")

    if not args.lichess and not args.chesscom:
        parser.error("Provide at least one source: --lichess and/or --chesscom")

    init_db()
    session_factory = make_session_factory()

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


if __name__ == "__main__":
    main()
