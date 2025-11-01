from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app import espn_client


@pytest.fixture()
def sample_client() -> espn_client.ESPNClient:
    return espn_client.ESPNClient(
        league_id=123456,
        season=2024,
        espn_s2="s2",
        swid="{SWID}",
    )


@pytest.fixture()
def canned_payloads():
    settings = {
        "status": {"latestScoringPeriod": 3},
        "settings": {
            "scheduleSettings": {"matchupPeriodCount": 14},
            "rosterSettings": {"lineupSlotCounts": {"0": 1, "2": 2, "20": 7}},
        },
    }

    teams = {
        "teams": [
            {
                "id": 1,
                "teamId": 1,
                "location": "Alpha",
                "nickname": "Squad",
                "owners": [{"displayName": "Owner One"}],
            },
            {
                "id": 2,
                "teamId": 2,
                "location": "Beta",
                "nickname": "Crew",
                "owners": [{"displayName": "Owner Two"}],
            },
        ]
    }

    matchups = {}
    for week in range(1, 6):
        matchups[week] = {
            "scoringPeriodId": week,
            "schedule": [
                {
                    "id": 70 + week,
                    "matchupPeriodId": week,
                    "home": {"teamId": 1, "totalPoints": 120.5},
                    "away": {"teamId": 2, "totalPoints": 98.3},
                    "winner": "HOME" if week <= 3 else "UNDECIDED",
                }
            ],
        }

    rosters = {
        2: {
            "teams": [
                {
                    "teamId": 1,
                    "roster": {
                        "entries": [
                            {
                                "lineupSlotId": 0,
                                "appliedStatTotal": 20.1,
                                "playerPoolEntry": {
                                    "player": {
                                        "fullName": "Player Alpha",
                                        "defaultPositionId": 1,
                                        "eligibleSlots": [0, 20],
                                    }
                                },
                            },
                            {
                                "lineupSlotId": 20,
                                "appliedStatTotal": 5.0,
                                "playerPoolEntry": {
                                    "player": {
                                        "fullName": "Bench Alpha",
                                        "defaultPositionId": 2,
                                        "eligibleSlots": [2, 20],
                                    }
                                },
                            },
                        ]
                    },
                },
                {
                    "teamId": 2,
                    "roster": {
                        "entries": [
                            {
                                "lineupSlotId": 2,
                                "appliedStatTotal": 15.6,
                                "playerPoolEntry": {
                                    "player": {
                                        "fullName": "Player Beta",
                                        "defaultPositionId": 3,
                                        "eligibleSlots": [2, 20],
                                    }
                                },
                            },
                            {
                                "lineupSlotId": 20,
                                "appliedStatTotal": 8.2,
                                "playerPoolEntry": {
                                    "player": {
                                        "fullName": "Bench Beta",
                                        "defaultPositionId": 4,
                                        "eligibleSlots": [4, 20],
                                    }
                                },
                            },
                        ]
                    },
                },
            ]
        }
    }

    return {
        "mSettings": settings,
        "mTeam": teams,
        "mMatchup": matchups,
        "mRoster": rosters,
    }


@pytest.fixture(autouse=True)
def stub_json_get(monkeypatch, canned_payloads):
    def _fake_json_get(path, params, cookies, *, retries=1):
        view = params.get("view")
        if view == "mMatchup":
            week = int(params.get("scoringPeriodId"))
            payload = canned_payloads[view].get(week, {"scoringPeriodId": week, "schedule": []})
            return copy.deepcopy(payload)
        if view == "mRoster":
            week = int(params.get("scoringPeriodId"))
            return copy.deepcopy(canned_payloads[view][week])
        return copy.deepcopy(canned_payloads[view])

    monkeypatch.setattr(espn_client, "_json_get", _fake_json_get)


def test_fetch_week_scores_uses_first_party_http(sample_client):
    scores = espn_client.fetch_week_scores(sample_client, week=2)

    assert len(scores) == 2

    for score in scores:
        assert score.week == 2
        assert score.points > 0
        assert score.owner.startswith("Owner")
        assert score.roster

    team_ids = {score.team_id for score in scores}
    assert team_ids == {1, 2}

    bench_lookup = {score.team_id: score.bench_points for score in scores}
    assert pytest.approx(bench_lookup[1], rel=1e-6) == 5.0
    assert pytest.approx(bench_lookup[2], rel=1e-6) == 8.2


def test_last_completed_week_respects_settings(sample_client):
    latest = espn_client.last_completed_week(sample_client, start_week=1)
    assert latest == 3
