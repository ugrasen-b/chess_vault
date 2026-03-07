# chess_vault

Local-first chess game vault for importing games from Lichess and Chess.com, then building analysis features over one unified dataset.

## Current MVP

- SQLite local database for games and sync state
- CLI sync command for Lichess and Chess.com public APIs
- Game header normalization (PGN tags)
- Player report command (W/L/D, top openings, source split)
- Opening-family normalization and family-level win-rate stats
- Incremental foundations (sync state table)

## Setup

```bash
uv sync
```

Or with pip:

```bash
python -m venv .venv
. .venv/Scripts/activate
pip install -e .[dev]
```

## Usage

```bash
chess-vault sync --lichess your_lichess_username --chesscom your_chesscom_username
chess-vault report --player your_username --top 10 --min-family-games 5
chess-vault analyze --player your_username --source chesscom --max-games 50 --depth 12
chess-vault mistakes --player your_username --type thrown_advantage --limit 20
```

Engine analysis requires a local Stockfish binary available as `stockfish` on your PATH, or pass `--engine-path`.

## Local UI (Streamlit)

```bash
uv sync --extra dev
uv run streamlit run src/chess_vault/ui/app.py
```

The UI includes:
- Dashboard (totals + recent analysis runs)
- Report (openings + family performance for a player)
- Mistakes (table view with game context and FEN)
- Sidebar actions for Sync and Analyze

Optional env vars:

- `CHESS_VAULT_DB_URL` default: `sqlite:///./data/chess_vault.db`
- `LICHESS_TOKEN` optional for authenticated Lichess API usage later

## Next Steps

1. Add robust PGN move parsing and derived features.
2. Add sync cursor logic for Lichess (`since`/timestamps) and retries/backoff.
3. Add pitfalls layer (recurring losses/pattern clusters by time control and opening family).
4. Add engine integration layer.
