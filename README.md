# chess_vault

Local-first chess game vault for importing games from Lichess and Chess.com, then building analysis features over one unified dataset.

## Current MVP

- SQLite local database for games and sync state
- CLI sync command for Lichess and Chess.com public APIs
- Game header normalization (PGN tags)
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
```

Optional env vars:

- `CHESS_VAULT_DB_URL` default: `sqlite:///./data/chess_vault.db`
- `LICHESS_TOKEN` optional for authenticated Lichess API usage later

## Next Steps

1. Add robust PGN move parsing and derived features.
2. Add sync cursor logic for Lichess (`since`/timestamps) and retries/backoff.
3. Add first analytics outputs (openings, common errors, time trouble).
4. Add engine integration layer.
