from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.efficiency import EffStat, format_efficiency_table, update_efficiency
from app.espn_client import TeamWeekScore


def test_update_efficiency_streaming_totals():
    stats: dict[int, EffStat] = {}
    seen_pairs: set[tuple[int, int]] = set()
    labels = {
        1: "Team One",
        2: "Team Two",
        3: "Team Three",
    }

    week_one = [
        TeamWeekScore(team_id=1, owner="One", week=1, points=100.0, optimal_points=110.0),
        TeamWeekScore(team_id=2, owner="Two", week=1, points=90.0, optimal_points=100.0),
        TeamWeekScore(team_id=3, owner="Three", week=1, points=80.0, optimal_points=120.0),
        TeamWeekScore(team_id=2, owner="Two", week=1, points=999.0, optimal_points=999.0),
    ]
    week_two = [
        TeamWeekScore(team_id=1, owner="One", week=2, points=95.0, optimal_points=115.0),
        TeamWeekScore(team_id=2, owner="Two", week=2, points=105.0, optimal_points=105.0),
        TeamWeekScore(team_id=3, owner="Three", week=2, points=70.0, optimal_points=140.0),
    ]

    update_efficiency(stats, week_one, seen=seen_pairs)
    update_efficiency(stats, week_two, seen=seen_pairs)

    assert stats[1].actual_sum == 195.0
    assert stats[1].optimal_sum == 225.0
    assert stats[2].actual_sum == 195.0
    assert stats[2].optimal_sum == 205.0
    assert stats[3].actual_sum == 150.0
    assert stats[3].optimal_sum == 260.0

    assert stats[1].efficiency == 195.0 / 225.0
    assert stats[2].efficiency == 195.0 / 205.0
    assert stats[3].efficiency == 150.0 / 260.0

    report = format_efficiency_table(labels, stats)
    lines = report.splitlines()
    assert lines[0] == "Season Efficiency"
    assert "Actual" in lines[2]
    assert "Optimal" in lines[2]
    assert "%" in lines[2]
    data_rows = [
        line
        for line in lines
        if line
        and not line.startswith(("Season", "`", "-"))
        and "Actual" not in line
    ]
    assert len(data_rows) == 3
