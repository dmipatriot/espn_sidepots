from __future__ import annotations
from typing import Any, Dict, Iterable, List, Tuple

import pandas as pd

from app.espn_client import label_for

def _apply_tiebreaks(
    df: pd.DataFrame,
    tiebreaks: Iterable[str] | None,
    base_sort: List[Tuple[str, bool]],
) -> pd.DataFrame:
    sort_columns: List[str] = []
    ascending: List[bool] = []
    for column, asc in base_sort:
        sort_columns.append(column)
        ascending.append(asc)

    rule_map: Dict[str, Tuple[str, bool]] = {
        "earliest_week": ("week", True),
        "latest_week": ("week", False),
        "higher_bench": ("bench_points", False),
        "alphabetical": ("owner", True),
    }

    for rule in tiebreaks or []:
        if rule not in rule_map:
            continue
        column, asc = rule_map[rule]
        sort_columns.append(column)
        ascending.append(asc)

    return df.sort_values(sort_columns, ascending=ascending, kind="mergesort")


def compute_pir(
    df: pd.DataFrame,
    *,
    target: float = 150.0,
    tiebreaks: List[str] | None = None,
    weeks_scope: List[int] | None = None,
    labels: Dict[int, str],
) -> Dict[str, Any]:
    """Return Price-Is-Right results constrained to the supplied week scope."""

    working = df.copy()
    if weeks_scope:
        working = working[working["week"].isin(weeks_scope)]

    working = working[["team_id", "owner", "week", "points", "bench_points"]].copy()
    working["owner"] = working["team_id"].apply(lambda tid: label_for(int(tid), labels))
    working["bench_points"] = working["bench_points"].fillna(0.0)
    working["delta"] = target - working["points"]
    candidates = working[working["delta"] >= 0].copy()
    leaderboard = _apply_tiebreaks(
        candidates, tiebreaks, base_sort=[("delta", True), ("points", False)]
    )

    leader_info: Dict[str, Any] | None = None
    if not leaderboard.empty:
        top = leaderboard.iloc[0]
        owner_display = label_for(int(top["team_id"]), labels)

        leader_info = {
            "team_id": int(top["team_id"]),
            "owner": owner_display,
            "week": int(top["week"]),
            "points": float(top["points"]),
            "delta": float(top["delta"]),
        }

    return {"leader": leader_info, "leaderboard_df": leaderboard.reset_index(drop=True)}
