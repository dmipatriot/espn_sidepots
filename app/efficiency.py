from __future__ import annotations
from typing import Dict, Any, List
import pandas as pd

def season_efficiency(
    df: pd.DataFrame,
    weeks: List[int],
    tiebreaks: List[str] | None = None,
) -> Dict[str, Any]:
    \"\"\"Compute season efficiency as mean of weekly efficiencies across given weeks.
    Inputs:
      df: must include ['team_id','owner','week','points','optimal_points','efficiency']
      weeks: list of regular-season weeks
      tiebreaks: order like ['higher_median','higher_total_points','alphabetical']

    Returns dict:
      {
        'table': pd.DataFrame,  # one row per team with season metrics
        'top_df': pd.DataFrame, # top 3
        'bottom_df': pd.DataFrame # bottom 3
      }
    Codex: implement.
    \"\"\"
    raise NotImplementedError
