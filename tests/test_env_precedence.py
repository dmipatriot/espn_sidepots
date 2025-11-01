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


def test_env_overrides_yaml_for_league_and_season(monkeypatch, tmp_path):
    monkeypatch.setenv("LEAGUE_ID", "999999")
    monkeypatch.setenv("SEASON", "2035")

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

    monkeypatch.setattr(main, "LOCK_PATH", tmp_path / "lockfile")

    monkeypatch.setattr(
        main,
        "parse_args",
        lambda: argparse.Namespace(mode="pir", weeks="auto", dry_run=True),
    )

    captured_preflight = {}
    captured_clients: list[main.ESPNClient] = []

    def fake_preflight(**kwargs):
        captured_preflight.update(kwargs)
        return {"status": "ok"}

    monkeypatch.setattr(main, "preflight_league", fake_preflight)
    monkeypatch.setattr(main, "extract_league_rules", lambda _client: {"regular_season_weeks": 14})
    monkeypatch.setattr(main, "last_completed_week", lambda _client: 1)
    monkeypatch.setattr(main, "get_weeks", lambda *_args, **_kwargs: [1])
    monkeypatch.setattr(
        main,
        "fetch_week_scores",
        lambda client, *_args, **_kwargs: captured_clients.append(client) or [],
    )
    monkeypatch.setattr(main, "build_base_frame", lambda payload: payload)
    monkeypatch.setattr(main, "add_optimal_points", lambda base, _rules: base)
    monkeypatch.setattr(main, "compute_pir", lambda *_args, **_kwargs: {"leaderboard_df": _EmptyFrame()})
    monkeypatch.setattr(main, "_maybe_post", lambda *_args, **_kwargs: None)

    main.main()

    assert captured_clients, "expected fetch_week_scores to receive a client"
    assert captured_clients[0].league_id == 999999
    assert captured_clients[0].season == 2035
    assert captured_preflight["league_id"] == 999999
    assert captured_preflight["season"] == 2035
