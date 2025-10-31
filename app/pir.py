from __future__ import annotations
from typing import Dict, Any, List
import pandas as pd

def compute_pir(
    df: pd.DataFrame,
    target: float = 150.0,
    tiebreaks: List[str] | None = None,
    weeks_scope: List[int] | None = None,
) -> Dict[str, Any]:
    \"\"\"Price-Is-Right: closest weekly 'points' to target without going over.
    Inputs:
      df: per-team-week DataFrame. Requires ['team_id','owner','week','points','bench_points'].
      target: default 150.0
      tiebreaks: list of tiebreak keys (e.g., ['earliest_week','higher_bench','alphabetical'])
      weeks_scope: optional list of week ints to constrain to regular season.

    Returns dict:
      {
        'leader': {'team_id', 'owner', 'week', 'points', 'delta'},
        'leaderboard_df': pd.DataFrame  # top N rows sorted by smallest delta
      }
    Codex: implement.
    \"\"\"
    raise NotImplementedError
