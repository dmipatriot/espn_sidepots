import argparse
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app import main


class _EmptyFrame:
    def head(self, _count):
        return self

    def iterrows(self):
        return iter(())


def test_league_id_env_precedence(monkeypatch):
    monkeypatch.setenv("LEAGUE_ID", "999999")

    monkeypatch.setattr(
        main,
        "load_config",
        lambda: {
            "league_id": 111111,
            "season": 2024,
            "tiebreaks": {},
            "pir_target": 150.0,
        },
    )

    monkeypatch.setattr(
        main,
        "parse_args",
        lambda: argparse.Namespace(mode="pir", weeks="auto", dry_run=True),
    )

    captured = {}

    def fake_get_league(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(main, "get_league", fake_get_league)
    monkeypatch.setattr(main, "extract_league_rules", lambda _league: {})
    monkeypatch.setattr(main, "last_completed_week", lambda _league: 1)
    monkeypatch.setattr(main, "get_weeks", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(main, "fetch_week_scores", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(main, "build_base_frame", lambda payload: payload)
    monkeypatch.setattr(main, "add_optimal_points", lambda base, _rules: base)
    monkeypatch.setattr(main, "compute_pir", lambda *_args, **_kwargs: {"leaderboard_df": _EmptyFrame()})
    monkeypatch.setattr(main, "_maybe_post", lambda *_args, **_kwargs: None)

    main.main()

    assert captured["league_id"] == 999999
