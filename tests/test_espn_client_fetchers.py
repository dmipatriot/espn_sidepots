import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app import espn_client
from app.efficiency import EffStat, format_efficiency_table, update_efficiency


def _make_player_entry(slot_id, name, position_id, points, *, eligible=None):
    return {
        "lineupSlotId": slot_id,
        "playerPoolEntry": {
            "player": {
                "fullName": name,
                "defaultPositionId": position_id,
                "eligibleSlots": list(eligible or []),
                "stats": [
                    {
                        "scoringPeriodId": 2,
                        "statSourceId": 0,
                        "appliedTotal": points,
                    }
                ],
            }
        },
        "appliedStatTotal": points,
    }


def test_fetch_week_scores_from_json(monkeypatch):
    client = espn_client.ESPNClient(league_id=123, season=2024, espn_s2="s", swid="{S}")

    matchups_payload = {
        "scoringPeriodId": 2,
        "schedule": [
            {
                "matchupPeriodId": 2,
                "home": {"teamId": 1, "totalPoints": 47.0, "nickname": "Alpha"},
                "away": {"teamId": 2, "totalPoints": 37.0, "nickname": "Beta"},
            }
        ],
    }

    rosters_payload = {
        "teams": [
            {
                "id": 1,
                "nickname": "Alpha",
                "location": "City",
                "roster": {
                    "entries": [
                        _make_player_entry(0, "QB One", 0, 20.0, eligible=[0, 7]),
                        _make_player_entry(2, "RB One", 2, 15.0),
                        _make_player_entry(4, "WR One", 4, 12.0),
                        _make_player_entry(20, "Bench RB", 2, 18.0),
                    ]
                },
            },
            {
                "id": 2,
                "nickname": "Beta",
                "location": "Town",
                "roster": {
                    "entries": [
                        _make_player_entry(0, "QB Two", 0, 18.0, eligible=[0, 7]),
                        _make_player_entry(2, "RB Two", 2, 10.0),
                        _make_player_entry(23, "Flex WR", 4, 9.0),
                        _make_player_entry(20, "Bench WR", 4, 16.0),
                    ]
                },
            },
        ]
    }

    monkeypatch.setattr(espn_client, "fetch_week_matchups", lambda _c, _w: matchups_payload)
    monkeypatch.setattr(espn_client, "fetch_week_rosters", lambda _c, _w: rosters_payload)

    scores = espn_client.fetch_week_scores(client, week=2)

    assert len(scores) == 2
    assert {score.team_id for score in scores} == {1, 2}
    assert {score.week for score in scores} == {2}

    team_map = {score.team_id: score for score in scores}
    team1 = team_map[1]
    team2 = team_map[2]

    assert team1.points == pytest.approx(47.0)
    assert team1.bench_points == pytest.approx(18.0)
    assert team1.optimal_points >= team1.points
    assert team1.roster and all("name" in entry for entry in team1.roster)

    assert team2.points == pytest.approx(37.0)
    assert team2.bench_points == pytest.approx(16.0)
    assert team2.optimal_points >= team2.points
    assert team2.roster and all("slot" in entry for entry in team2.roster)

    stats_store: dict[int, EffStat] = {}
    seen: set[tuple[int, int]] = set()
    update_efficiency(stats_store, scores, seen=seen)
    table = format_efficiency_table({1: "Alpha", 2: "Beta"}, stats_store)

    assert "Alpha" in table
    assert "Beta" in table
    assert table.count("Alpha") == 1
    assert table.count("Beta") == 1


def test_last_completed_week_respects_settings():
     client = espn_client.ESPNClient(league_id=1, season=2024, espn_s2="s", swid="{S}")
     monkeypatched = {}

     def _fake_fetch_settings(_client):
         return {
             "status": {"latestScoringPeriod": 3},
             "settings": {
                 "scheduleSettings": {"matchupPeriodCount": 5},
             },
         }

     def _fake_fetch_week_matchups(_client, week):
         monkeypatched[week] = True
         winner = "HOME" if week <= 3 else "UNDECIDED"
         return {
             "scoringPeriodId": week,
             "schedule": [
                 {"matchupPeriodId": week, "home": {"teamId": 1}, "away": {"teamId": 2}, "winner": winner}
             ],
         }

     original_fetch_settings = espn_client.fetch_settings
     original_fetch_week_matchups = espn_client.fetch_week_matchups
     try:
         espn_client.fetch_settings = _fake_fetch_settings
         espn_client.fetch_week_matchups = _fake_fetch_week_matchups
         latest = espn_client.last_completed_week(client, start_week=1)
     finally:
         espn_client.fetch_settings = original_fetch_settings
         espn_client.fetch_week_matchups = original_fetch_week_matchups

     assert latest == 3
