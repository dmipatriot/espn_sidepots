from __future__ import annotations
from typing import Dict, Any, List
import pandas as pd

# === Contract ===
# Codex will:
# - Convert raw week payloads into a tidy DataFrame with columns at minimum:
#   ['team_id','owner','week','points','bench_points','roster'] where
#   'roster' is a list[dict] of {player_id, pos, eligible_slots, points}.
# - Implement an optimal lineup solver that respects ESPN slot limits
#   (incl. FLEX/SUPERFLEX). Prefer exact (ILP/backtracking) over greedy.

BASE_COLUMNS = [
    "team_id", "owner", "week", "points", "bench_points", "roster"
]

def build_base_frame(weeks_payload: List[Dict[str, Any]]) -> pd.DataFrame:
    \"\"\"Codex: implement.
    Input is a list of dicts per team-week built from espn_client.
    Output DataFrame must include BASE_COLUMNS.
    \"\"\"
    raise NotImplementedError


def add_optimal_points(df: pd.DataFrame, league_rules: Dict[str, Any]) -> pd.DataFrame:
    \"\"\"Codex: implement.
    Given base df and roster/slot rules for that week (from ESPN),
    compute 'optimal_points' and add 'efficiency' = points/optimal_points (clip to 1.0 if desired).
    Return a NEW DataFrame (do not mutate caller reference).
    \"\"\"
    raise NotImplementedError
