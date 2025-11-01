from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app import espn_client


class _FakePlayer:
    def __init__(self, name: str, slot: str, points: float, position: str, eligible=None):
        self.name = name
        self.slot_position = slot
        self.points = points
        self.position = position
        self.eligibleSlots = list(eligible or [position])


class _FakeBoxScore:
    def __init__(
        self,
        home_team: int,
        home_score: float,
        home_lineup,
        away_team: int,
        away_score: float,
        away_lineup,
    ) -> None:
        self.home_team = home_team
        self.home_score = home_score
        self.home_lineup = home_lineup
        self.away_team = away_team
        self.away_score = away_score
        self.away_lineup = away_lineup


class _FakeTeam:
    def __init__(self, team_id: int, owner: str, name: str) -> None:
        self.team_id = team_id
        self.owner = owner
        self.team_name = name


class _FakeLeague:
    def __init__(self, teams, box_scores_by_week):
        self.teams = teams
        self._box_scores_by_week = box_scores_by_week

    def box_scores(self, week):
        return list(self._box_scores_by_week.get(week, []))


@pytest.fixture()
def sample_league():
    qb1 = _FakePlayer("QB One", "QB", 25.0, "QB")
    rb1 = _FakePlayer("RB One", "RB", 10.0, "RB")
    flex1 = _FakePlayer("Flex WR", "RB/WR/TE", 5.0, "WR")
    bench_star = _FakePlayer("Bench RB", "BE", 30.0, "RB")
    bench_k = _FakePlayer("Bench K", "BN", 8.0, "K")

    qb2 = _FakePlayer("QB Two", "QB", 15.0, "QB")
    wr2 = _FakePlayer("WR Two", "WR", 20.0, "WR")
    te2 = _FakePlayer("TE Two", "TE", 7.0, "TE")
    op2 = _FakePlayer("Super Flex", "OP", 2.0, "RB")
    bench_qb = _FakePlayer("Bench QB", "BE", 25.0, "QB")
    bench_wr = _FakePlayer("Bench WR", "BE", 12.0, "WR")

    box = _FakeBoxScore(
        home_team=1,
        home_score=40.0,
        home_lineup=[qb1, rb1, flex1, bench_star, bench_k],
        away_team=2,
        away_score=44.0,
        away_lineup=[qb2, wr2, te2, op2, bench_qb, bench_wr],
    )

    teams = [_FakeTeam(1, "Owner One", "Alpha Squad"), _FakeTeam(2, "Owner Two", "Beta Crew")]
    return _FakeLeague(teams, {2: [box]})


def test_fetch_week_scores_from_boxscores(sample_league):
    scores = espn_client.fetch_week_scores(sample_league, week=2)

    assert len(scores) == 2
    team_lookup = {score.team_id: score for score in scores}

    team1 = team_lookup[1]
    assert team1.owner == "Owner One"
    assert pytest.approx(team1.points, rel=1e-6) == 40.0
    assert pytest.approx(team1.bench_points, rel=1e-6) == 38.0
    assert team1.optimal_points > team1.points
    assert team1.roster and len(team1.roster) == 5

    team2 = team_lookup[2]
    assert team2.owner == "Owner Two"
    assert pytest.approx(team2.points, rel=1e-6) == 44.0
    assert pytest.approx(team2.bench_points, rel=1e-6) == 37.0
    assert team2.optimal_points > team2.points
    assert team2.roster and len(team2.roster) == 6


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
