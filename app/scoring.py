from __future__ import annotations
from typing import Dict, Any, List
import pandas as pd

BASE_COLUMNS = ["team_id","owner","week","points","bench_points","roster"]

def build_base_frame(weeks_payload: List[Dict[str, Any]]) -> pd.DataFrame:
    """Codex: implement. Input is list of dicts per team-week. Output includes BASE_COLUMNS."""
    raise NotImplementedError

def add_optimal_points(df: pd.DataFrame, league_rules: Dict[str, Any]) -> pd.DataFrame:
    """Codex: implement. Compute 'optimal_points' and 'efficiency' respecting roster rules."""
    raise NotImplementedError
