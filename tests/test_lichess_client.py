from chess_vault.ingest.lichess_client import _build_request_params, _split_pgn_batch


def test_split_pgn_batch_splits_multiple_games() -> None:
    payload = """
[Event "Rated Blitz game"]
[Site "https://lichess.org/abc123"]
[White "alice"]
[Black "bob"]
[Result "1-0"]

1. e4 e5 1-0

[Event "Rated Rapid game"]
[Site "https://lichess.org/def456"]
[White "carol"]
[Black "dave"]
[Result "0-1"]

1. d4 d5 0-1
""".strip()

    games = _split_pgn_batch(payload)

    assert len(games) == 2
    assert '[Site "https://lichess.org/abc123"]' in games[0]
    assert '[Site "https://lichess.org/def456"]' in games[1]


def test_build_request_params_omits_max_when_unlimited() -> None:
    assert "max" not in _build_request_params(None)
    assert "max" not in _build_request_params(0)
    assert "max" not in _build_request_params(-5)


def test_build_request_params_includes_max_when_positive() -> None:
    params = _build_request_params(50)
    assert params["max"] == 50
