from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.espn_client import build_team_label_map
from app.main import _format_survivor_summary
from app.survivor import run_survivor


def test_build_team_label_map_uses_preferred_fields():
    teams_payload = {
        "teams": [
            {
                "id": 1,
                "abbrev": "ABC",
                "location": "Alpha",
                "nickname": "Squad",
            },
            {
                "id": 2,
                "owners": [{"displayName": "Owner Two"}],
            },
        ]
    }

    labels = build_team_label_map(teams_payload)

    assert labels[1] == "ABC — Alpha Squad"
    assert labels[2] == "Owner Two"


def test_survivor_summary_uses_labels():
    df = pd.DataFrame(
        [
            {
                "team_id": 1,
                "owner": "Owner One",
                "week": 1,
                "points": 120.0,
                "optimal_points": 150.0,
                "efficiency": 0.8,
            },
            {
                "team_id": 2,
                "owner": "Owner Two",
                "week": 1,
                "points": 90.0,
                "optimal_points": 150.0,
                "efficiency": 0.6,
            },
        ]
    )
    labels = {1: "AAA — Alpha Squad", 2: "BBB — Bravo Crew"}

    result = run_survivor(df, start_week=1, weeks_scope=[1], labels=labels)

    assert labels[2] in result["summary"][0]

    formatted = _format_survivor_summary(result, labels)
    assert any(labels[2] in line for line in formatted)
    assert any(labels[1] in line for line in formatted)
