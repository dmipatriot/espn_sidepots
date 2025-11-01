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


def test_main_smoke(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "LOCK_PATH", tmp_path / "lock")
    monkeypatch.setattr(
        main,
        "load_config",
        lambda: {
            "league_id": 123,
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

    monkeypatch.setattr(main, "preflight_league", lambda **_kwargs: {"status": "ok"})
    monkeypatch.setattr(main, "extract_league_rules", lambda _client: {"regular_season_weeks": 14})
    monkeypatch.setattr(main, "last_completed_week", lambda _client: 1)
    monkeypatch.setattr(main, "get_weeks", lambda *_args, **_kwargs: [1])
    monkeypatch.setattr(main, "fetch_week_scores", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(main, "build_base_frame", lambda payload: payload)
    monkeypatch.setattr(main, "add_optimal_points", lambda base, _rules: base)
    monkeypatch.setattr(main, "compute_pir", lambda *_args, **_kwargs: {"leaderboard_df": _EmptyFrame()})

    posts: list[tuple] = []
    monkeypatch.setattr(main, "_maybe_post", lambda *args, **_kwargs: posts.append(args))

    main.main()

    assert posts, "Expected PIR report to trigger posting logic"
