from __future__ import annotations
from typing import Any, Dict, Iterable, List, Tuple

import logging
import pandas as pd

from app.espn_client import label_for


LOGGER = logging.getLogger(__name__)


def _resolve_tiebreak(
    candidates: List[int],
    tiebreaks: Iterable[str] | None,
    owner_map: Dict[int, str],
    cumulative: Dict[str, Dict[int, float]],
) -> int:
    if len(candidates) == 1:
        return candidates[0]

    ordering: List[Tuple[str, bool, Dict[int, float]]] = []
    rule_map: Dict[str, Tuple[str, bool]] = {
        "lower_season_eff": ("season_efficiency", True),
        "higher_season_eff": ("season_efficiency", False),
        "lower_total_points": ("total_points", True),
        "higher_total_points": ("total_points", False),
        "alphabetical": ("alphabetical", True),
    }

    for rule in tiebreaks or []:
        if rule not in rule_map:
            continue
        key, asc = rule_map[rule]
        if key == "alphabetical":
            ordering.append((key, asc, {team: owner_map.get(team, "") for team in candidates}))
        else:
            ordering.append((key, asc, cumulative[key]))

    if not ordering:
        # Deterministic fallback: alphabetical (owner display)
        ordering.append(("alphabetical", True, {team: owner_map.get(team, "") for team in candidates}))

    remaining = candidates[:]
    for key, asc, metric in ordering:
        values = {team: metric.get(team, 0.0) if key != "alphabetical" else metric.get(team, "") for team in remaining}
        best_value = min(values.values()) if asc else max(values.values())
        remaining = [team for team, value in values.items() if value == best_value]
        if len(remaining) == 1:
            return remaining[0]

    return sorted(remaining, key=lambda tid: owner_map.get(tid, ""))[0]


def run_survivor(
    df: pd.DataFrame,
    *,
    start_week: int = 3,
    tiebreaks: List[str] | None = None,
    weeks_scope: List[int] | None = None,
    last_completed_week: int | None = None,
    labels: Dict[int, str],
) -> Dict[str, Any]:
    """Simulate a season-long survivor pool with deterministic tie handling."""

    if weeks_scope:
        weeks = sorted({int(week) for week in weeks_scope})
    else:
        weeks = sorted({int(week) for week in df["week"].unique()})

    teams = sorted({int(team_id) for team_id in df["team_id"].unique()})
    owner_map: Dict[int, str] = {
        team: label_for(team, labels) for team in teams
    }

    cumulative_eff: Dict[int, List[float]] = {team: [] for team in teams}
    cumulative_points: Dict[int, float] = {team: 0.0 for team in teams}

    alive: List[int] = teams[:]
    eliminated: List[Dict[str, Any]] = []
    eliminations: List[Tuple[int, int, float]] = []
    summary: List[str] = []

    if not weeks:
        return {"eliminations": eliminations, "eliminated_order": eliminated, "alive": alive, "summary": summary}

    first_week = min(weeks)
    last_week = last_completed_week if last_completed_week is not None else max(weeks)
    if last_week < first_week:
        return {"eliminations": eliminations, "eliminated_order": eliminated, "alive": alive, "summary": summary}

    weeks_set = set(weeks)

    for week in range(first_week, last_week + 1):
        if week not in weeks_set:
            continue
        week_rows = df[df["week"] == week]
        week_scores = {int(row["team_id"]): float(row["points"]) for _, row in week_rows.iterrows()}
        week_effs = {int(row["team_id"]): float(row.get("efficiency", 0.0)) for _, row in week_rows.iterrows()}
        week_opt = {int(row["team_id"]): float(row.get("optimal_points", row["points"])) for _, row in week_rows.iterrows()}

        for team in teams:
            score = week_scores.get(team, 0.0)
            eff = week_effs.get(team, 0.0)
            opt = week_opt.get(team, 0.0) or 0.0
            cumulative_points[team] += score
            if opt > 0:
                cumulative_eff[team].append(score / opt)
            elif eff:
                cumulative_eff[team].append(eff)

        if week < start_week or len(alive) <= 1:
            continue

        alive_scores = {team: week_scores.get(team, 0.0) for team in alive}
        if not any(team in week_scores for team in alive):
            LOGGER.warning("No survivor scores for alive teams in week %s; skipping elimination", week)
            continue
        min_score = min(alive_scores.values())
        low_teams = [team for team, score in alive_scores.items() if score == min_score]

        cumulative_metrics = {
            "season_efficiency": {
                team: (sum(cumulative_eff[team]) / len(cumulative_eff[team]) if cumulative_eff[team] else 0.0)
                for team in teams
            },
            "total_points": cumulative_points,
        }

        # Tiebreak order: points -> season efficiency -> season points -> alphabetical label
        loser = _resolve_tiebreak(low_teams, tiebreaks, owner_map, cumulative_metrics)
        alive.remove(loser)
        eliminated_points = alive_scores.get(loser, 0.0)
        eliminations.append((week, loser, eliminated_points))
        eliminated.append(
            {
                "week": week,
                "team_id": loser,
                "owner": owner_map.get(loser, label_for(loser, labels)),
                "points": eliminated_points,
            }
        )
        summary.append(
            f"Week {week}: {label_for(int(loser), labels)} eliminated ({eliminated_points:.2f})"
        )

    return {
        "eliminations": eliminations,
        "eliminated_order": eliminated,
        "alive": alive,
        "summary": summary,
    }
