from __future__ import annotations

import copy
from pathlib import Path

import pandas as pd
import pytest

import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app import espn_client
from app.survivor import run_survivor


@pytest.fixture()
def survivor_client() -> espn_client.ESPNClient:
    return espn_client.ESPNClient(
        league_id=987654,
        season=2024,
        espn_s2="s2",
        swid="{SWID}",
    )


def test_survivor_inclusive_through_week_eight(monkeypatch, survivor_client):
    settings_payload = {
        "settings": {"scheduleSettings": {"matchupPeriodCount": 14}},
        "status": {"latestScoringPeriod": 8},
    }
    monkeypatch.setattr(espn_client, "fetch_settings", lambda _client: settings_payload)

    matchups_by_week: dict[int, dict] = {}
    for week in range(3, 9):
        matchups_by_week[week] = {
            "scoringPeriodId": week,
            "schedule": [
                {
                    "matchupPeriodId": week,
                    "winner": "HOME",
                }
            ],
        }
    matchups_by_week[9] = {
        "scoringPeriodId": 9,
        "schedule": [
            {
                "matchupPeriodId": 9,
                "winner": "UNDECIDED",
            }
        ],
    }

    def fake_fetch_matchups(_client, week: int) -> dict:
        payload = matchups_by_week.get(week, {"scoringPeriodId": week, "schedule": []})
        return copy.deepcopy(payload)

    monkeypatch.setattr(espn_client, "fetch_week_matchups", fake_fetch_matchups)

    lcw = espn_client.last_completed_week(survivor_client, start_week=3, end_week=10)
    assert lcw == 8

    elimination_map = {3: 7, 4: 6, 5: 5, 6: 4, 7: 3, 8: 2}
    rows: list[dict] = []
    for week in range(1, 9):
        loser_team = elimination_map.get(week)
        for team in range(1, 8):
            points = 100.0 + team
            if week >= 3 and team == loser_team:
                points = 40.0 + week
            rows.append(
                {
                    "team_id": team,
                    "owner": f"Team {team}",
                    "week": week,
                    "points": points,
                    "optimal_points": 150.0,
                    "efficiency": points / 150.0,
                }
            )

    df = pd.DataFrame(rows)
    labels = {team: f"Team {team}" for team in range(1, 8)}

    result = run_survivor(
        df,
        start_week=3,
        tiebreaks=["lower_season_eff", "lower_total_points", "alphabetical"],
        weeks_scope=list(range(1, 9)),
        last_completed_week=lcw,
        labels=labels,
    )

    losers_by_week = {week: team for week, team, _ in result["eliminations"]}
    assert losers_by_week[8] == elimination_map[8]
    assert elimination_map[8] not in result["alive"]
    assert any(line.startswith("Week 8:") for line in result["summary"])
