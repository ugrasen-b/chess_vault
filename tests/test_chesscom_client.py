from chess_vault.ingest.chesscom_client import _select_archives


def test_select_archives_caps_to_most_recent_n() -> None:
    archives = [
        "https://api.chess.com/pub/player/x/games/2024/01",
        "https://api.chess.com/pub/player/x/games/2024/02",
        "https://api.chess.com/pub/player/x/games/2024/03",
    ]
    selected = _select_archives(archives, max_months=2)
    assert selected == [archives[2], archives[1]]


def test_select_archives_returns_all_when_unlimited() -> None:
    archives = [
        "https://api.chess.com/pub/player/x/games/2024/01",
        "https://api.chess.com/pub/player/x/games/2024/02",
    ]
    assert _select_archives(archives, max_months=None) == list(reversed(archives))
    assert _select_archives(archives, max_months=0) == list(reversed(archives))
