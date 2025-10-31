from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.efficiency import season_efficiency
from app.pir import compute_pir
from app.scoring import add_optimal_points, build_base_frame
from app.survivor import run_survivor


def _make_payload(roster, points=100.0, week=1, team_id=1, owner="Owner"):
    return {
        "team_id": team_id,
        "owner": owner,
        "week": week,
        "points": points,
        "bench_points": 0.0,
        "roster": roster,
    }


def test_optimal_flex_solver_beats_greedy():
    roster = [
        {"name": "QB1", "points": 20.0, "slot": "QB", "eligible_slots": ["QB", "OP"]},
        {"name": "RB1", "points": 25.0, "slot": "RB", "eligible_slots": ["RB", "RB/WR/TE", "OP"]},
        {"name": "RB2", "points": 20.0, "slot": "RB", "eligible_slots": ["RB", "RB/WR/TE", "OP"]},
        {"name": "RB3", "points": 18.0, "slot": "RB", "eligible_slots": ["RB", "RB/WR/TE", "OP"]},
        {"name": "WR1", "points": 19.0, "slot": "WR", "eligible_slots": ["WR", "RB/WR/TE", "OP"]},
        {"name": "WR2", "points": 18.0, "slot": "WR", "eligible_slots": ["WR", "RB/WR/TE", "OP"]},
        {"name": "WR3", "points": 16.0, "slot": "WR", "eligible_slots": ["WR", "RB/WR/TE", "OP"]},
        {"name": "TE1", "points": 30.0, "slot": "TE", "eligible_slots": ["TE", "RB/WR/TE", "OP"]},
        {"name": "TE2", "points": 5.0, "slot": "TE", "eligible_slots": ["TE", "RB/WR/TE", "OP"]},
    ]
    payload = [_make_payload(roster)]
    df = build_base_frame(payload)
    rules = {"slot_counts": {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "RB/WR/TE": 1}}
    scored = add_optimal_points(df, rules)
    optimal = scored.loc[0, "optimal_points"]

    slots = ["RB/WR/TE", "QB", "RB", "RB", "WR", "WR", "TE"]
    greedy_total = 0.0
    remaining_slots = slots.copy()
    for player in sorted(roster, key=lambda p: p["points"], reverse=True):
        for slot in list(remaining_slots):
            if slot in player["eligible_slots"]:
                greedy_total += player["points"]
                remaining_slots.remove(slot)
                break

    assert pytest.approx(optimal, rel=1e-6) == 150.0
    assert greedy_total == 137.0
    assert optimal > greedy_total


def test_price_is_right_tiebreaks():
    df = pd.DataFrame(
        [
            {"team_id": 1, "owner": "Alice", "week": 2, "points": 149.0, "bench_points": 12.0},
            {"team_id": 2, "owner": "Bob", "week": 1, "points": 149.0, "bench_points": 10.0},
            {"team_id": 3, "owner": "Cara", "week": 3, "points": 147.0, "bench_points": 20.0},
        ]
    )
    result = compute_pir(
        df,
        target=150.0,
        tiebreaks=["earliest_week", "higher_bench", "alphabetical"],
        weeks_scope=[1, 2, 3],
    )
    assert result["leader"]["owner"] == "Bob"
    leaderboard = result["leaderboard_df"]
    assert list(leaderboard["owner"]) == ["Bob", "Alice", "Cara"]


def test_efficiency_tiebreak_chain():
    rows = []
    for week, effs in enumerate([(1.0, 0.95), (0.8, 0.95), (0.9, 0.8)], start=1):
        team_a_eff, team_b_eff = effs
        rows.append(
            {
                "team_id": 1,
                "owner": "Alpha",
                "week": week,
                "points": team_a_eff * 100,
                "optimal_points": 100.0,
                "efficiency": team_a_eff,
            }
        )
        rows.append(
            {
                "team_id": 2,
                "owner": "Beta",
                "week": week,
                "points": team_b_eff * 100,
                "optimal_points": 100.0,
                "efficiency": team_b_eff,
            }
        )
    df = pd.DataFrame(rows)
    result = season_efficiency(df, weeks=[1, 2, 3], tiebreaks=["higher_median", "higher_total_points", "alphabetical"])
    table = result["table"]
    assert table.iloc[0]["owner"] == "Beta"
    assert pytest.approx(table.iloc[0]["season_efficiency"], rel=1e-6) == pytest.approx(table.iloc[1]["season_efficiency"], rel=1e-6)


def test_survivor_elimination_with_tiebreaks():
    rows = []
    # Week 1 establishes efficiencies
    rows.extend(
        [
            {"team_id": 1, "owner": "Alpha", "week": 1, "points": 120.0, "optimal_points": 150.0, "efficiency": 0.8},
            {"team_id": 2, "owner": "Bravo", "week": 1, "points": 130.0, "optimal_points": 150.0, "efficiency": 0.867},
            {"team_id": 3, "owner": "Charlie", "week": 1, "points": 110.0, "optimal_points": 150.0, "efficiency": 0.733},
        ]
    )
    # Week 2 tie for lowest score -> Charlie eliminated on lowest season efficiency
    rows.extend(
        [
            {"team_id": 1, "owner": "Alpha", "week": 2, "points": 90.0, "optimal_points": 150.0, "efficiency": 0.6},
            {"team_id": 2, "owner": "Bravo", "week": 2, "points": 90.0, "optimal_points": 150.0, "efficiency": 0.6},
            {"team_id": 3, "owner": "Charlie", "week": 2, "points": 90.0, "optimal_points": 150.0, "efficiency": 0.6},
        ]
    )
    # Week 3 tie resolved by lower total points
    rows.extend(
        [
            {"team_id": 1, "owner": "Alpha", "week": 3, "points": 80.0, "optimal_points": 150.0, "efficiency": 0.533},
            {"team_id": 2, "owner": "Bravo", "week": 3, "points": 70.0, "optimal_points": 150.0, "efficiency": 0.467},
        ]
    )
    df = pd.DataFrame(rows)
    result = run_survivor(
        df,
        start_week=2,
        tiebreaks=["lower_season_eff", "lower_total_points", "alphabetical"],
        weeks_scope=[1, 2, 3],
    )
    eliminated = result["eliminated_order"]
    assert eliminated[0]["owner"] == "Charlie"
    assert eliminated[1]["owner"] == "Bravo"
    assert result["alive"] == [1]


def test_survivor_handles_missing_weeks():
    df = pd.DataFrame(
        [
            {"team_id": 1, "owner": "Alpha", "week": 1, "points": 100.0, "optimal_points": 150.0, "efficiency": 0.667},
            {"team_id": 2, "owner": "Bravo", "week": 1, "points": 90.0, "optimal_points": 150.0, "efficiency": 0.6},
            # Week 2 missing for Alpha -> treated as zero and eliminated
            {"team_id": 2, "owner": "Bravo", "week": 2, "points": 80.0, "optimal_points": 150.0, "efficiency": 0.533},
        ]
    )
    result = run_survivor(
        df,
        start_week=2,
        tiebreaks=["lower_total_points", "alphabetical"],
        weeks_scope=[1, 2],
    )
    assert result["eliminated_order"][0]["owner"] == "Alpha"
