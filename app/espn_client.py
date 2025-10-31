from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any

@dataclass(frozen=True)
class TeamWeekScore:
    team_id: int
    owner: str
    week: int
    points: float
    bench_points: float | None = None
    raw: Dict[str, Any] | None = None

def get_league(league_id: int, season: int, espn_s2: str, swid: str):
    """Return an espn_api League instance. Codex: implement."""
    raise NotImplementedError

def get_weeks(weeks_spec: str, regular_season_weeks: int, last_completed: int | None = None) -> List[int]:
    """Parse --weeks ('auto'|'N'|'A-B'|'A,B,C') to a sorted list within 1..regular_season_weeks."""
    raise NotImplementedError

def fetch_week_scores(league, week: int) -> List[TeamWeekScore]:
    """Return per-team scoring for a specific week using league.box_scores(week)."""
    raise NotImplementedError

def last_completed_week(league) -> int:
    """Return last completed (fully scored) week for the season."""
    raise NotImplementedError
