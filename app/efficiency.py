from __future__ import annotations
from typing import Dict, Any, List
import pandas as pd

def season_efficiency(
    df: pd.DataFrame,
    weeks: List[int],
    tiebreaks: List[str] | None = None,
) -> Dict[str, Any]:
    """Compute season efficiency as mean of weekly efficiencies across given weeks.
    df must include: ['team_id','owner','week','points','optimal_points','efficiency'].
    Returns dict with 'table', 'top_df', 'bottom_df'.
    """
    raise NotImplementedError
