from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Set, Tuple


@dataclass
class EffStat:
    team_id: int
    actual_sum: float = 0.0
    optimal_sum: float = 0.0
    weeks: int = 0

    @property
    def efficiency(self) -> float:
        return (self.actual_sum / self.optimal_sum) if self.optimal_sum > 0 else 0.0


def update_efficiency(
    stats: Dict[int, EffStat],
    week_scores: List["TeamWeekScore"],
    *,
    seen: Set[Tuple[int, int]],
) -> None:
    """
    Accumulate per-week actual/optimal per team. Enforce exactly one record per (team_id, week).
    If a duplicate slips in, skip it (duplicates are the likely cause of 2x optimal).
    """

    for score in week_scores:
        key = (int(score.team_id), int(score.week))
        if key in seen:
            continue
        seen.add(key)

        entry = stats.setdefault(score.team_id, EffStat(team_id=score.team_id))
        entry.actual_sum += float(score.points or 0.0)
        entry.optimal_sum += float(getattr(score, "optimal_points", 0.0) or 0.0)
        entry.weeks += 1


def format_efficiency_table(labels: Dict[int, str], stats: Dict[int, EffStat]) -> str:
    """
    Render all teams in a monospaced table: Team, Actual, Optimal, Eff%.
    """

    rows = sorted(stats.values(), key=lambda stat: stat.efficiency, reverse=True)
    header = f"{'Team':<28} {'Actual':>7} {'Optimal':>8} {'Eff%':>7}"
    lines = ["Season Efficiency", "```", header, "-" * len(header)]
    for entry in rows:
        name = labels.get(entry.team_id, f"Team {entry.team_id}")
        lines.append(
            f"{name:<28} {entry.actual_sum:7.1f} {entry.optimal_sum:8.1f} {entry.efficiency*100:7.2f}%"
        )
    lines.append("```")
    return "\n".join(lines)

