from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from app.espn_client import TeamWeekScore


@dataclass
class EffStat:
    team_id: int
    actual_sum: float = 0.0
    optimal_sum: float = 0.0
    weeks: int = 0

    @property
    def efficiency(self) -> float:
        return (self.actual_sum / self.optimal_sum) if self.optimal_sum > 0 else 0.0


def update_efficiency(stats: Dict[int, EffStat], week_scores: List[TeamWeekScore]) -> None:
    for score in week_scores:
        entry = stats.setdefault(score.team_id, EffStat(team_id=score.team_id))
        entry.actual_sum += float(score.points or 0.0)
        entry.optimal_sum += float(score.optimal_points or 0.0)
        entry.weeks += 1


def format_efficiency_report(labels: Dict[int, str], stats: Dict[int, EffStat]) -> str:
    rows = sorted(stats.values(), key=lambda stat: stat.efficiency, reverse=True)
    lines = ["Season Efficiency"]
    for entry in rows:
        name = labels.get(entry.team_id, f"Team {entry.team_id}")
        lines.append(
            f"{name}: Actual {entry.actual_sum:.1f} | Optimal {entry.optimal_sum:.1f} | Eff {entry.efficiency*100:.2f}%"
        )
    return "\n".join(lines)

