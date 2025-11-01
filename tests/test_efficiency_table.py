import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.efficiency import EffStat, format_efficiency_table, update_efficiency
from app.espn_client import TeamWeekScore


def _score(team_id: int, week: int, actual: float, optimal: float) -> TeamWeekScore:
    return TeamWeekScore(
        team_id=team_id,
        owner=f"Owner {team_id}",
        week=week,
        points=actual,
        optimal_points=optimal,
    )


def test_update_efficiency_skips_duplicates_and_formats_table():
    scores = [
        _score(1, 1, 100.0, 120.0),
        _score(1, 1, 200.0, 300.0),  # duplicate should be ignored
        _score(1, 2, 90.0, 110.0),
        _score(2, 1, 95.0, 100.0),
        _score(2, 2, 105.0, 130.0),
        _score(3, 1, 80.0, 90.0),
        _score(3, 2, 85.0, 100.0),
    ]

    stats: dict[int, EffStat] = {}
    seen: set[tuple[int, int]] = set()
    update_efficiency(stats, scores, seen=seen)

    assert stats[1].weeks == 2
    assert stats[2].weeks == 2
    assert stats[3].weeks == 2

    assert stats[1].actual_sum == 190.0
    assert stats[1].optimal_sum == 230.0
    assert stats[2].actual_sum == 200.0
    assert stats[2].optimal_sum == 230.0
    assert stats[3].actual_sum == 165.0
    assert stats[3].optimal_sum == 190.0

    assert stats[1].efficiency == 190.0 / 230.0
    assert stats[2].efficiency == 200.0 / 230.0
    assert stats[3].efficiency == 165.0 / 190.0

    table = format_efficiency_table(
        {1: "Team One", 2: "Team Two", 3: "Team Three"}, stats
    )
    lines = table.splitlines()
    assert lines[0] == "Season Efficiency"
    assert "Actual" in lines[2]
    assert "Optimal" in lines[2]
    assert "Eff%" in lines[2]

    body_lines = [
        line for line in lines if line.startswith("Team") and "Actual" not in line
    ]
    assert len(body_lines) == 3
    for line in body_lines:
        assert "Actual" not in line  # ensure data lines not header duplicates
        assert line.strip().endswith("%")
