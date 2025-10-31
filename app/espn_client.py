from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, List, Dict, Any, Tuple
import os

# NOTE: Codex implements actual ESPN client using espn_api. Keep signatures.

@dataclass(frozen=True)
class TeamWeekScore:
    team_id: int
    owner: str
    week: int
    points: float
    bench_points: float | None = None
    # optional raw payload for debugging
    raw: Dict[str, Any] | None = None


def get_league(league_id: int, season: int, espn_s2: str, swid: str):
    \"\"\"Return an espn_api League instance. Codex: implement.\"\"\"
    raise NotImplementedError


def get_weeks(weeks_spec: str, regular_season_weeks: int, last_completed: int | None = None) -> List[int]:
    \"\"\"Parse --weeks ('auto'|'N'|'A-B'|'A,B,C') -> sorted list of ints within 1..regular_season_weeks.
    If weeks_spec == 'auto', use last_completed (Codex derives from league) clipped to regular season.\"\"\"
    raise NotImplementedError


def fetch_week_scores(league, week: int) -> List[TeamWeekScore]:
    \"\"\"Return per-team scoring for a specific week. Codex: implement via league.box_scores(week).
    Must map team_id, owner display name, total points, and bench points.\"\"\"
    raise NotImplementedError


def last_completed_week(league) -> int:
    \"\"\"Return last completed (fully scored) week for the season. Codex: implement.\"\"\"
    raise NotImplementedError
