from __future__ import annotations
from typing import Dict, Any, List
import pandas as pd

def run_survivor(
    df: pd.DataFrame,
    start_week: int = 3,
    tiebreaks: List[str] | None = None,
    weeks_scope: List[int] | None = None,
) -> Dict[str, Any]:
    """Survivor pool: starting start_week, eliminate weekly lowest score among remaining teams.
    Returns dict with 'eliminated_order', 'alive', 'summary'.
    Deterministic: recompute from W1 each run.
    """
    raise NotImplementedError
