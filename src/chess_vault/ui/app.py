from __future__ import annotations

from collections.abc import Sequence
from io import StringIO

import chess
import chess.pgn
import chess.svg
import streamlit as st
import streamlit.components.v1 as components
from sqlalchemy import desc, func, select

from chess_vault.analysis.analyze_service import AnalysisService, is_mate_score
from chess_vault.analysis.explorer import lookup_position, position_key_from_fen
from chess_vault.analysis.features import build_player_report
from chess_vault.analysis.repertoire import RepertoireService
from chess_vault.db.models import AnalysisRun, EngineEval, Game, GameMistake
from chess_vault.db.session import init_db, make_session_factory
from chess_vault.ingest.sync_service import SyncService
from chess_vault.ui.chessboard import chessboard, legal_dests


def _to_table(items: Sequence[tuple[str, int]], key_name: str) -> list[dict[str, int | str]]:
    return [{key_name: name, "count": count} for name, count in items]


def _extract_mainline_uci(raw_pgn: str) -> list[str]:
    game = chess.pgn.read_game(StringIO(raw_pgn))
    if game is None:
        return []
    return [move.uci() for move in game.mainline_moves()]


def _extract_mainline_san(raw_pgn: str) -> list[str]:
    game = chess.pgn.read_game(StringIO(raw_pgn))
    if game is None:
        return []

    board = game.board()
    sans: list[str] = []
    for move in game.mainline_moves():
        sans.append(board.san(move))
        board.push(move)
    return sans


def _board_before_ply(raw_pgn: str, ply: int) -> chess.Board:
    board = chess.Board()
    moves = _extract_mainline_uci(raw_pgn)
    # "before ply N" means apply N-1 plies from the start position.
    plies_to_apply = max(0, min(len(moves), ply - 1))
    for uci in moves[:plies_to_apply]:
        board.push_uci(uci)
    return board


def _render_svg_board(
    board: chess.Board,
    size: int = 420,
    orientation: chess.Color = chess.WHITE,
    lastmove: chess.Move | None = None,
    arrows: list[chess.svg.Arrow] | None = None,
) -> None:
    svg = chess.svg.board(
        board=board,
        size=size,
        orientation=orientation,
        lastmove=lastmove,
        arrows=arrows or [],
        coordinates=True,
    )
    components.html(svg, height=size + 10)


def _lookup_best_move_uci(session, mistake: GameMistake) -> str | None:
    run = session.execute(
        select(AnalysisRun).where(AnalysisRun.id == mistake.analysis_run_id).limit(1)
    ).scalar_one_or_none()
    if run is None:
        return None

    exact = session.execute(
        select(EngineEval)
        .where(
            EngineEval.fen == mistake.fen,
            EngineEval.depth == run.depth,
            EngineEval.engine_name == run.engine_name,
            EngineEval.engine_version == run.engine_version,
        )
        .limit(1)
    ).scalar_one_or_none()
    if exact and exact.best_move_uci:
        return exact.best_move_uci

    fallback = session.execute(
        select(EngineEval).where(EngineEval.fen == mistake.fen).order_by(desc(EngineEval.id)).limit(1)
    ).scalar_one_or_none()
    if fallback and fallback.best_move_uci:
        return fallback.best_move_uci
    return None


def _render_sidebar() -> tuple[str, int, int]:
    st.sidebar.header("Player Settings")
    player = st.sidebar.text_input("Player", value="ugrasen")
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
        max_games = int(
            st.number_input(
                "Lichess Max Games", min_value=0, max_value=100000, value=100, help="0 = fetch all games"
            )
        )
        max_months = int(
            st.number_input(
                "Chess.com Max Months", min_value=0, max_value=240, value=6, step=1, help="0 = fetch all months"
            )
        )
        if st.button("Sync Now"):
            with session_factory() as session:
                service = SyncService(session)
                if lichess_user.strip():
                    result = service.sync_lichess(
                        lichess_user.strip(), max_games=None if max_games == 0 else max_games
                    )
                    st.success(
                        f"Lichess: fetched={result.fetched} inserted={result.inserted} "
                        f"skipped={result.skipped_existing}"
                    )
                if chesscom_user.strip():
                    result = service.sync_chesscom(
                        chesscom_user.strip(), max_months=None if max_months == 0 else max_months
                    )
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
    min_swing = int(
        st.number_input("Minimum Swing (cp)", min_value=0, max_value=200000, value=0, step=25)
    )

    with session_factory() as session:
        service = AnalysisService(session)
        mistakes = service.list_mistakes(
            player=player,
            category=category,
            limit=500,
            latest_run_only=True,
            dedupe_by_game=True,
        )
        filtered = [m for m in mistakes if m.swing_cp >= min_swing][:limit]
        if not filtered:
            rows: list[tuple[GameMistake, Game]] = []
        else:
            game_ids = [m.game_id for m in filtered]
            games = session.execute(select(Game).where(Game.id.in_(game_ids))).scalars().all()
            game_map = {g.id: g for g in games}
            rows = [(m, game_map[m.game_id]) for m in filtered if m.game_id in game_map]

    table = [
        {
            "id": idx + 1,
            "game_id": mistake.game_id,
            "source": game.source,
            "opening": game.opening or "(Unknown)",
            "played_at": game.played_at,
            "ply": mistake.ply,
            "move": mistake.move_uci,
            "before_cp": mistake.before_eval_cp,
            "after_cp": mistake.after_eval_cp,
            "swing_cp": mistake.swing_cp,
            "mate_swing": "yes"
            if is_mate_score(mistake.before_eval_cp) or is_mate_score(mistake.after_eval_cp)
            else "no",
            "fen": mistake.fen,
        }
        for idx, (mistake, game) in enumerate(rows)
    ]
    st.dataframe(table, use_container_width=True)

    if not rows:
        return

    st.markdown("**Mistake Detail**")
    labels = [
        (
            f"#{idx + 1} game={mistake.game_id} ply={mistake.ply} "
            f"swing={mistake.swing_cp} move={mistake.move_uci}"
        )
        for idx, (mistake, _game) in enumerate(rows)
    ]
    selected_label = st.selectbox("Select mistake", options=labels, index=0)
    selected_index = labels.index(selected_label)
    selected_mistake, selected_game = rows[selected_index]
    with session_factory() as session:
        best_move_uci = _lookup_best_move_uci(session, selected_mistake)

    c1, c2 = st.columns(2)
    c1.write(f"Game ID: `{selected_game.id}`")
    c1.write(f"Source: `{selected_game.source}`")
    c1.write(f"Opening: `{selected_game.opening or '(Unknown)'}`")
    c1.write(f"Players: `{selected_game.white_player}` vs `{selected_game.black_player}`")
    c2.write(f"Ply: `{selected_mistake.ply}`")
    c2.write(f"Move: `{selected_mistake.move_uci}`")
    c2.write(f"Before: `{selected_mistake.before_eval_cp}`")
    c2.write(f"After: `{selected_mistake.after_eval_cp}`")
    c2.write(f"Swing: `{selected_mistake.swing_cp}`")
    c2.write(
        f"Mate Swing: `{'yes' if (is_mate_score(selected_mistake.before_eval_cp) or is_mate_score(selected_mistake.after_eval_cp)) else 'no'}`"
    )
    c2.write(f"Best Move (engine): `{best_move_uci or 'n/a'}`")

    st.markdown("Position at detected mistake (from stored FEN)")
    fen_board = chess.Board(selected_mistake.fen)
    board_size = int(st.slider("Board Size", min_value=280, max_value=720, value=480, step=20))
    orientation_label = st.selectbox("Board Orientation", options=["White", "Black"], index=0)
    orientation = chess.WHITE if orientation_label == "White" else chess.BLACK

    try:
        detected_move = chess.Move.from_uci(selected_mistake.move_uci)
    except ValueError:
        detected_move = None
    try:
        best_move = chess.Move.from_uci(best_move_uci) if best_move_uci else None
    except ValueError:
        best_move = None
    arrows: list[chess.svg.Arrow] = []
    if detected_move and detected_move in fen_board.legal_moves:
        arrows.append(chess.svg.Arrow(detected_move.from_square, detected_move.to_square, color="#d62828"))
    if best_move and best_move in fen_board.legal_moves:
        arrows.append(chess.svg.Arrow(best_move.from_square, best_move.to_square, color="#2a9d8f"))

    _render_svg_board(
        fen_board,
        size=board_size,
        orientation=orientation,
        lastmove=detected_move if (detected_move and detected_move in fen_board.legal_moves) else None,
        arrows=arrows,
    )
    st.caption("Arrows: red = played move, green = engine best move")
    st.caption(f"FEN: {selected_mistake.fen}")

    moves = _extract_mainline_uci(selected_game.raw_pgn)
    san_moves = _extract_mainline_san(selected_game.raw_pgn)
    if moves:
        jump_ply = int(
            st.slider(
                "Jump to board before ply",
                min_value=1,
                max_value=len(moves) + 1,
                value=min(selected_mistake.ply, len(moves) + 1),
                step=1,
            )
        )
        jump_board = _board_before_ply(selected_game.raw_pgn, jump_ply)
        st.markdown(f"Board before ply `{jump_ply}`")
        jump_lastmove = None
        if jump_ply > 1 and jump_ply - 2 < len(moves):
            jump_lastmove = chess.Move.from_uci(moves[jump_ply - 2])
        _render_svg_board(
            jump_board,
            size=board_size,
            orientation=orientation,
            lastmove=jump_lastmove,
        )

        move_rows = []
        for idx, uci in enumerate(moves):
            ply = idx + 1
            move_no = (idx // 2) + 1
            side = "W" if (idx % 2) == 0 else "B"
            san = san_moves[idx] if idx < len(san_moves) else ""
            marker = "<-- detected" if ply == selected_mistake.ply else ""
            move_rows.append(
                {
                    "ply": ply,
                    "move_no": move_no,
                    "side": side,
                    "san": san,
                    "uci": uci,
                    "flag": marker,
                }
            )

        st.markdown("Mainline moves (SAN + UCI)")
        st.dataframe(move_rows, use_container_width=True, height=240)

    with st.expander("Raw PGN"):
        st.code(selected_game.raw_pgn, language="text")


def _format_movetext(sans: list[str]) -> str:
    parts = []
    for idx, san in enumerate(sans):
        parts.append(f"{idx // 2 + 1}.{san}" if idx % 2 == 0 else san)
    return " ".join(parts)


def _render_result_bar(white_wins: int, draws: int, black_wins: int, height: int = 18) -> None:
    total = white_wins + draws + black_wins
    if total == 0:
        return
    segments = [
        (white_wins / total * 100, "#e8e8e8", "#333"),
        (draws / total * 100, "#9e9e9e", "#fff"),
        (black_wins / total * 100, "#4a4a4a", "#fff"),
    ]
    cells = "".join(
        f'<div style="width:{pct:.4f}%;background:{bg};color:{fg};">'
        f'{f"{pct:.0f}%" if pct >= 12 else ""}</div>'
        for pct, bg, fg in segments
    )
    st.markdown(
        f'<div style="display:flex;width:100%;height:{height}px;border-radius:4px;'
        f'overflow:hidden;font-size:11px;line-height:{height}px;text-align:center;">{cells}</div>',
        unsafe_allow_html=True,
    )


def _render_opening_explorer(session_factory, player: str) -> None:
    st.subheader("Opening Explorer")
    st.caption("Play through the board to see how often you've reached this position and what came next.")
    if not player:
        st.info("Enter a player in the sidebar.")
        return

    if "explorer_moves" not in st.session_state:
        st.session_state.explorer_moves = []

    control_cols = st.columns(2)
    perspective_label = control_cols[0].selectbox(
        "Perspective", options=["Both", "White", "Black"], key="explorer_perspective"
    )
    orientation_label = control_cols[1].selectbox(
        "Orientation", options=["White", "Black"], key="explorer_orientation"
    )

    board = chess.Board()
    san_moves: list[str] = []
    for uci in st.session_state.explorer_moves:
        move = chess.Move.from_uci(uci)
        san_moves.append(board.san(move))
        board.push(move)

    last_move = None
    if st.session_state.explorer_moves:
        last_uci = st.session_state.explorer_moves[-1]
        last_move = (last_uci[0:2], last_uci[2:4])

    board_col, table_col = st.columns([1, 1])

    with board_col:
        result = chessboard(
            fen=board.fen(),
            orientation=orientation_label.lower(),
            dests=legal_dests(board),
            last_move=last_move,
            size=420,
            key="explorer_board",
        )

        if result and not board.is_game_over():
            orig = chess.parse_square(result["orig"])
            dest = chess.parse_square(result["dest"])
            move = chess.Move(orig, dest)
            if move not in board.legal_moves:
                # Pawn reaching the last rank needs a promotion piece; auto-queen for now.
                move = chess.Move(orig, dest, promotion=chess.QUEEN)
            if move in board.legal_moves:
                st.session_state.explorer_moves.append(move.uci())
                st.rerun()

        nav_cols = st.columns(2)
        if nav_cols[0].button(
            "Back", disabled=not st.session_state.explorer_moves, use_container_width=True
        ):
            st.session_state.explorer_moves.pop()
            st.rerun()
        if nav_cols[1].button(
            "Reset", disabled=not st.session_state.explorer_moves, use_container_width=True
        ):
            st.session_state.explorer_moves = []
            st.rerun()

        st.caption(_format_movetext(san_moves) if san_moves else "Start position")
        st.caption(f"FEN: {board.fen()}")

    perspective = None if perspective_label == "Both" else perspective_label.lower()
    with session_factory() as session:
        stats = lookup_position(session=session, player=player, moves=san_moves, perspective=perspective)

    with table_col:
        scope_note = f" (as {perspective_label})" if perspective else ""
        st.markdown(f"**{stats.total_games}** of your games reached this position{scope_note}")
        if stats.total_games:
            _render_result_bar(stats.white_wins, stats.draws, stats.black_wins)
            st.caption(f"White {stats.white_wins} · Draws {stats.draws} · Black {stats.black_wins}")

        if not stats.next_moves:
            st.info("No games in your history continue from here.")
            return

        st.markdown("**Next moves**")
        header = st.columns([1, 1, 4, 1])
        header[0].caption("Move")
        header[1].caption("Games")
        header[2].caption("Result")
        for move in stats.next_moves:
            row = st.columns([1, 1, 4, 1])
            row[0].write(f"**{move.move_san}**")
            row[1].write(str(move.games))
            with row[2]:
                _render_result_bar(move.white_wins, move.draws, move.black_wins, height=14)
            if row[3].button("Play", key=f"explorer_play_{move.move_uci}"):
                st.session_state.explorer_moves.append(move.move_uci)
                st.rerun()


def _render_repertoire(session_factory) -> None:
    st.subheader("Repertoire")
    st.caption(
        "Build a named repertoire by playing lines on the board and annotating moves. "
        "Use Back to return to an earlier position and play an alternative to branch."
    )

    with session_factory() as session:
        repertoires = RepertoireService(session).list_repertoires()
        rep_options = {f"{r.name} ({r.side})": r.id for r in repertoires}

    with st.expander("Create a new repertoire", expanded=not repertoires):
        new_name = st.text_input("Name", value="", key="rep_new_name")
        new_side = st.selectbox("Side", options=["white", "black", "both"], key="rep_new_side")
        if st.button("Create repertoire"):
            if not new_name.strip():
                st.error("Name is required.")
            elif new_name.strip() in {r.name for r in repertoires}:
                st.error("A repertoire with that name already exists.")
            else:
                with session_factory() as session:
                    RepertoireService(session).create_repertoire(new_name.strip(), new_side)
                st.rerun()

    if not rep_options:
        st.info("Create a repertoire to start adding lines.")
        return

    selected_label = st.selectbox("Active repertoire", options=list(rep_options.keys()))
    repertoire_id = rep_options[selected_label]

    if "rep_moves" not in st.session_state:
        st.session_state.rep_moves = []

    board = chess.Board()
    san_moves: list[str] = []
    for uci in st.session_state.rep_moves:
        move = chess.Move.from_uci(uci)
        san_moves.append(board.san(move))
        board.push(move)

    last_move = None
    if st.session_state.rep_moves:
        last_uci = st.session_state.rep_moves[-1]
        last_move = (last_uci[0:2], last_uci[2:4])

    orientation_label = st.selectbox("Orientation", options=["White", "Black"], key="rep_orient")

    board_col, edit_col = st.columns([1, 1])

    with board_col:
        result = chessboard(
            fen=board.fen(),
            orientation=orientation_label.lower(),
            dests=legal_dests(board),
            last_move=last_move,
            size=420,
            key="rep_board",
        )
        if result and not board.is_game_over():
            orig = chess.parse_square(result["orig"])
            dest = chess.parse_square(result["dest"])
            move = chess.Move(orig, dest)
            if move not in board.legal_moves:
                move = chess.Move(orig, dest, promotion=chess.QUEEN)
            if move in board.legal_moves:
                st.session_state.rep_moves.append(move.uci())
                st.rerun()

        nav_cols = st.columns(2)
        if nav_cols[0].button(
            "Back", disabled=not st.session_state.rep_moves, use_container_width=True, key="rep_back"
        ):
            st.session_state.rep_moves.pop()
            st.rerun()
        if nav_cols[1].button(
            "Clear board", disabled=not st.session_state.rep_moves, use_container_width=True, key="rep_clear"
        ):
            st.session_state.rep_moves = []
            st.rerun()

        st.caption(_format_movetext(san_moves) if san_moves else "Start position")

        # Show what this repertoire already knows at the current position.
        with session_factory() as session:
            known = RepertoireService(session).book_moves_at(
                repertoire_id, position_key_from_fen(board.fen())
            )
        if known:
            st.caption("Already in book here: " + ", ".join(m.move_san for m in known))

    with edit_col:
        if not san_moves:
            st.info("Play moves on the board to build a line, then add notes and save.")
        else:
            st.markdown("**Notes for this line** (optional, per move)")
            for index, san in enumerate(san_moves):
                move_no = index // 2 + 1
                label = f"{move_no}.{san}" if index % 2 == 0 else f"{move_no}...{san}"
                st.text_input(label, key=f"rep_note_{index}")

            if st.button("Save line to repertoire", type="primary"):
                comment_by_index = {
                    i: st.session_state.get(f"rep_note_{i}", "") for i in range(len(san_moves))
                }
                with session_factory() as session:
                    touched = RepertoireService(session).add_line(
                        repertoire_id, st.session_state.rep_moves, comment_by_index
                    )
                st.success(f"Saved {touched} move(s) into '{selected_label}'.")


def _render_board_demo() -> None:
    st.subheader("Board Demo")
    st.caption("Proving ground for the interactive chessground component — click or drag a piece.")

    if "board_demo_moves" not in st.session_state:
        st.session_state.board_demo_moves = []

    board = chess.Board()
    for uci in st.session_state.board_demo_moves:
        board.push_uci(uci)

    last_move = None
    if st.session_state.board_demo_moves:
        last_uci = st.session_state.board_demo_moves[-1]
        last_move = (last_uci[0:2], last_uci[2:4])

    orientation_label = st.selectbox("Orientation", options=["White", "Black"], index=0)

    result = chessboard(
        fen=board.fen(),
        orientation=orientation_label.lower(),
        dests=legal_dests(board),
        last_move=last_move,
        size=480,
        key="board_demo",
    )

    if result and not board.is_game_over():
        orig = chess.parse_square(result["orig"])
        dest = chess.parse_square(result["dest"])
        move = chess.Move(orig, dest)
        if move not in board.legal_moves:
            # Pawn reaching the last rank needs a promotion piece; auto-queen for now.
            move = chess.Move(orig, dest, promotion=chess.QUEEN)
        if move in board.legal_moves:
            san = board.san(move)
            board.push(move)
            st.session_state.board_demo_moves.append(move.uci())
            st.toast(f"Played {san}")
            st.rerun()

    if st.button("Reset board"):
        st.session_state.board_demo_moves = []
        st.rerun()

    if st.session_state.board_demo_moves:
        st.write("Moves: " + " ".join(st.session_state.board_demo_moves))


def main() -> None:
    st.set_page_config(page_title="Chess Vault", layout="wide")
    st.title("Chess Vault")

    init_db()
    session_factory = make_session_factory()

    player, top_n, min_family_games = _render_sidebar()
    _render_actions(session_factory)

    page = st.radio(
        "View",
        options=["Dashboard", "Report", "Mistakes", "Opening Explorer", "Repertoire", "Board Demo"],
        horizontal=True,
    )

    if page == "Dashboard":
        _render_dashboard(session_factory, player)
    elif page == "Report":
        _render_report(session_factory, player, top_n=top_n, min_family_games=min_family_games)
    elif page == "Mistakes":
        _render_mistakes(session_factory, player)
    elif page == "Opening Explorer":
        _render_opening_explorer(session_factory, player)
    elif page == "Repertoire":
        _render_repertoire(session_factory)
    else:
        _render_board_demo()


if __name__ == "__main__":
    main()
