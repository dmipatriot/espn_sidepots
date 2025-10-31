from __future__ import annotations
from typing import Dict, Iterable, List, Tuple

import pandas as pd


def _apply_efficiency_tiebreaks(
    df: pd.DataFrame,
    tiebreaks: Iterable[str] | None,
    base_sort: List[Tuple[str, bool]],
) -> pd.DataFrame:
    sort_columns: List[str] = [col for col, _ in base_sort]
    ascending: List[bool] = [asc for _, asc in base_sort]

    rule_map: Dict[str, Tuple[str, bool]] = {
        "higher_median": ("median_efficiency", False),
        "higher_total_points": ("total_points", False),
        "lower_total_points": ("total_points", True),
        "alphabetical": ("owner", True),
    }

    for rule in tiebreaks or []:
        if rule not in rule_map:
            continue
        column, asc = rule_map[rule]
        sort_columns.append(column)
        ascending.append(asc)

    return df.sort_values(sort_columns, ascending=ascending, kind="mergesort")


def season_efficiency(
    df: pd.DataFrame,
    weeks: List[int],
    tiebreaks: List[str] | None = None,
) -> Dict[str, Any]:
    """Aggregate weekly efficiency into season-long leaderboards."""

    subset = df[df["week"].isin(weeks)].copy()
    if subset.empty:
        empty = pd.DataFrame()
        return {"table": empty, "top_df": empty, "bottom_df": empty}

    grouped = subset.groupby(["team_id", "owner"], as_index=False).agg(
        games_played=("week", "nunique"),
        total_points=("points", "sum"),
        total_optimal=("optimal_points", "sum"),
        mean_efficiency=("efficiency", "mean"),
        median_efficiency=("efficiency", "median"),
    )
    grouped["season_efficiency"] = grouped["mean_efficiency"]

    ordered = _apply_efficiency_tiebreaks(
        grouped,
        tiebreaks,
        base_sort=[("season_efficiency", False), ("games_played", False)],
    ).reset_index(drop=True)

    top_df = ordered.head(3)
    bottom_df = ordered.tail(3)
    return {"table": ordered, "top_df": top_df, "bottom_df": bottom_df}
