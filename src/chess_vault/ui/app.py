from __future__ import annotations

from collections.abc import Sequence

import streamlit as st
from sqlalchemy import desc, func, select

from chess_vault.analysis.analyze_service import AnalysisService
from chess_vault.analysis.features import build_player_report
from chess_vault.db.models import AnalysisRun, Game, GameMistake
from chess_vault.db.session import init_db, make_session_factory
from chess_vault.ingest.sync_service import SyncService


def _to_table(items: Sequence[tuple[str, int]], key_name: str) -> list[dict[str, int | str]]:
    return [{key_name: name, "count": count} for name, count in items]


def _render_sidebar() -> tuple[str, int, int]:
    st.sidebar.header("Player Settings")
    player = st.sidebar.text_input("Player", value="uglyduckling24")
    top_n = st.sidebar.number_input("Top N", min_value=1, max_value=50, value=10, step=1)
    min_family_games = st.sidebar.number_input(
        "Min Family Games", min_value=1, max_value=100, value=5, step=1
    )
    return player.strip(), int(top_n), int(min_family_games)


def _render_actions(session_factory) -> None:
    st.sidebar.header("Actions")

    with st.sidebar.expander("Run Sync", expanded=False):
        lichess_user = st.text_input("Lichess Username", value="")
        chesscom_user = st.text_input("Chess.com Username", value="")
        max_games = int(st.number_input("Lichess Max Games", min_value=1, max_value=500, value=100))
        max_months = int(
            st.number_input("Chess.com Max Months", min_value=1, max_value=24, value=6, step=1)
        )
        if st.button("Sync Now"):
            with session_factory() as session:
                service = SyncService(session)
                if lichess_user.strip():
                    result = service.sync_lichess(lichess_user.strip(), max_games=max_games)
                    st.success(
                        f"Lichess: fetched={result.fetched} inserted={result.inserted} "
                        f"skipped={result.skipped_existing}"
                    )
                if chesscom_user.strip():
                    result = service.sync_chesscom(chesscom_user.strip(), max_months=max_months)
                    st.success(
                        f"Chess.com: fetched={result.fetched} inserted={result.inserted} "
                        f"skipped={result.skipped_existing}"
                    )

    with st.sidebar.expander("Run Analyze", expanded=False):
        source = st.selectbox("Source", options=["all", "lichess", "chesscom"], index=0)
        engine_path = st.text_input("Engine Path", value="stockfish")
        analyze_max_games = int(
            st.number_input("Analyze Max Games", min_value=1, max_value=500, value=50, step=1)
        )
        depth = int(st.number_input("Depth", min_value=1, max_value=30, value=12, step=1))
        win_threshold = int(
            st.number_input("Win Threshold (cp)", min_value=50, max_value=1000, value=200, step=10)
        )
        drop_to = int(st.number_input("Drop To (cp)", min_value=-1000, max_value=500, value=0, step=10))
        lookahead = int(
            st.number_input("Lookahead Plies", min_value=1, max_value=10, value=3, step=1)
        )
        analyze_player = st.text_input("Analyze Player", value="")
        if st.button("Analyze Now"):
            if not analyze_player.strip():
                st.error("Analyze Player is required.")
            else:
                with session_factory() as session:
                    service = AnalysisService(session)
                    try:
                        summary = service.analyze_player_games(
                            player=analyze_player.strip(),
                            source=None if source == "all" else source,
                            max_games=analyze_max_games,
                            engine_path=engine_path,
                            depth=depth,
                            win_threshold_cp=win_threshold,
                            drop_to_cp=drop_to,
                            lookahead_plies=lookahead,
                        )
                        st.success(
                            f"Run {summary.analysis_run_id}: scanned={summary.games_scanned} "
                            f"mistakes={summary.mistakes_found}"
                        )
                    except FileNotFoundError:
                        st.error("Engine not found. Set a valid Stockfish path in Engine Path.")


def _render_dashboard(session_factory, player: str) -> None:
    st.subheader("Dashboard")
    with session_factory() as session:
        total_games = session.execute(select(func.count()).select_from(Game)).scalar_one()
        total_mistakes = session.execute(select(func.count()).select_from(GameMistake)).scalar_one()
        latest_run = session.execute(select(AnalysisRun).order_by(desc(AnalysisRun.id)).limit(1)).scalar_one_or_none()

        c1, c2, c3 = st.columns(3)
        c1.metric("Total Games", int(total_games or 0))
        c2.metric("Stored Mistakes", int(total_mistakes or 0))
        c3.metric("Latest Run ID", int(latest_run.id) if latest_run else 0)

        if player:
            report = build_player_report(session=session, player=player, top_n=5, min_family_games=3)
            st.write(f"Current player summary: `{player}`")
            st.write(f"Games: {report.total_games} | W: {report.wins} | L: {report.losses} | D: {report.draws}")

        st.write("Recent analysis runs")
        runs = session.execute(select(AnalysisRun).order_by(desc(AnalysisRun.id)).limit(10)).scalars().all()
        run_rows = [
            {
                "run_id": row.id,
                "player": row.player,
                "source": row.source or "all",
                "status": row.status,
                "depth": row.depth,
                "games_scanned": row.games_scanned,
                "mistakes_found": row.mistakes_found,
                "started_at": row.started_at,
                "completed_at": row.completed_at,
            }
            for row in runs
        ]
        st.dataframe(run_rows, use_container_width=True)


def _render_report(session_factory, player: str, top_n: int, min_family_games: int) -> None:
    st.subheader("Report")
    if not player:
        st.info("Enter a player in the sidebar.")
        return

    with session_factory() as session:
        report = build_player_report(
            session=session,
            player=player,
            top_n=top_n,
            min_family_games=min_family_games,
        )

    st.write(f"Player: `{report.player}`")
    st.write(f"Games: {report.total_games} | W: {report.wins} | L: {report.losses} | D: {report.draws}")

    st.markdown("**By Source**")
    st.dataframe(_to_table(report.by_source, "source"), use_container_width=True)

    st.markdown("**Top Openings Played**")
    st.dataframe(_to_table(report.top_openings_played, "opening"), use_container_width=True)

    st.markdown("**Top Opponent Openings Against You**")
    st.dataframe(_to_table(report.top_opponent_openings_against_you, "opening"), use_container_width=True)

    st.markdown("**Top Opening Families Played**")
    st.dataframe(_to_table(report.top_opening_families_played, "family"), use_container_width=True)

    st.markdown("**Opening Family Performance**")
    perf_rows = [
        {
            "family": row.family,
            "games": row.games,
            "wins": row.wins,
            "losses": row.losses,
            "draws": row.draws,
            "win_rate": round(row.win_rate, 1),
        }
        for row in report.opening_family_performance
    ]
    st.dataframe(perf_rows, use_container_width=True)


def _render_mistakes(session_factory, player: str) -> None:
    st.subheader("Mistakes")
    if not player:
        st.info("Enter a player in the sidebar.")
        return

    limit = int(st.number_input("Limit", min_value=1, max_value=200, value=30, step=1))
    category = st.selectbox("Category", options=["thrown_advantage"], index=0)

    with session_factory() as session:
        stmt = (
            select(GameMistake, Game)
            .join(Game, GameMistake.game_id == Game.id)
            .where(
                func.lower(GameMistake.player) == player.lower(),
                GameMistake.category == category,
            )
            .order_by(desc(GameMistake.swing_cp))
            .limit(limit)
        )
        rows = session.execute(stmt).all()

    table = [
        {
            "game_id": mistake.game_id,
            "source": game.source,
            "opening": game.opening or "(Unknown)",
            "played_at": game.played_at,
            "ply": mistake.ply,
            "move": mistake.move_uci,
            "before_cp": mistake.before_eval_cp,
            "after_cp": mistake.after_eval_cp,
            "swing_cp": mistake.swing_cp,
            "fen": mistake.fen,
        }
        for mistake, game in rows
    ]
    st.dataframe(table, use_container_width=True)


def main() -> None:
    st.set_page_config(page_title="Chess Vault", layout="wide")
    st.title("Chess Vault")

    init_db()
    session_factory = make_session_factory()

    player, top_n, min_family_games = _render_sidebar()
    _render_actions(session_factory)

    page = st.radio(
        "View",
        options=["Dashboard", "Report", "Mistakes"],
        horizontal=True,
    )

    if page == "Dashboard":
        _render_dashboard(session_factory, player)
    elif page == "Report":
        _render_report(session_factory, player, top_n=top_n, min_family_games=min_family_games)
    else:
        _render_mistakes(session_factory, player)


if __name__ == "__main__":
    main()
