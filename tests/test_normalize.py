from chess_vault.ingest.normalize import normalize_pgn


def test_normalize_pgn_extracts_basic_headers() -> None:
    pgn = '''
[Event "Live Chess"]
[Site "https://www.chess.com/game/live/123456789"]
[Date "2026.02.20"]
[White "alice"]
[Black "bob"]
[Result "1-0"]
[TimeControl "600+0"]
[ECO "C20"]
[Opening "King's Pawn Game"]

1. e4 e5 2. Nf3 Nc6 1-0
'''.strip()

    game = normalize_pgn(source="chesscom", raw_pgn=pgn)

    assert game.source == "chesscom"
    assert game.source_game_id == "https://www.chess.com/game/live/123456789"
    assert game.white_player == "alice"
    assert game.black_player == "bob"
    assert game.result == "1-0"
    assert game.time_control == "600+0"
    assert game.eco == "C20"
    assert game.opening == "King's Pawn Game"
    assert game.played_at is not None


def test_normalize_pgn_uses_hash_when_site_is_not_unique() -> None:
    pgn_a = '''
[Event "Live Chess"]
[Site "Chess.com"]
[Date "2026.02.20"]
[White "alice"]
[Black "bob"]
[Result "1-0"]

1. e4 e5 2. Nf3 Nc6 1-0
'''.strip()
    pgn_b = '''
[Event "Live Chess"]
[Site "Chess.com"]
[Date "2026.02.21"]
[White "alice"]
[Black "bob"]
[Result "0-1"]

1. d4 d5 2. c4 e6 0-1
'''.strip()

    game_a = normalize_pgn(source="chesscom", raw_pgn=pgn_a)
    game_b = normalize_pgn(source="chesscom", raw_pgn=pgn_b)

    assert game_a.source_game_id != "Chess.com"
    assert game_b.source_game_id != "Chess.com"
    assert game_a.source_game_id != game_b.source_game_id
