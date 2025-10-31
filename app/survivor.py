from __future__ import annotations
from typing import Dict, Any, List
import pandas as pd

def run_survivor(
    df: pd.DataFrame,
    start_week: int = 3,
    tiebreaks: List[str] | None = None,
    weeks_scope: List[int] | None = None,
) -> Dict[str, Any]:
    \"\"\"Survivor pool: starting start_week, eliminate weekly lowest score among remaining teams.
    Inputs:
      df: per-team-week DataFrame with ['team_id','owner','week','points','efficiency'] (eff for tie-breaks)
      start_week: first elimination week
      tiebreaks: e.g., ['lower_season_eff','lower_total_points','alphabetical']
      weeks_scope: optional explicit list of weeks to iterate

    Returns dict:
      {
        'eliminated_order': List[{'team_id','owner','week','points'}],
        'alive': List[{'team_id','owner'}],
        'summary': str
      }
    Codex: implement deterministically by recomputing from W1 each run.
    \"\"\"
    raise NotImplementedError
