from __future__ import annotations
from typing import Any, Dict, Iterable, List, Sequence

import pandas as pd


BASE_COLUMNS = ["team_id", "owner", "week", "points", "bench_points", "roster"]


def build_base_frame(weeks_payload: List[Dict[str, Any]]) -> pd.DataFrame:
    """Return a normalized per-team-week DataFrame."""

    if not weeks_payload:
        return pd.DataFrame(columns=BASE_COLUMNS)

    records: List[Dict[str, Any]] = []
    for entry in weeks_payload:
        record = {key: entry.get(key) for key in BASE_COLUMNS}
        # Normalize numeric fields.
        record["points"] = float(record.get("points") or 0.0)
        bench = record.get("bench_points")
        record["bench_points"] = None if bench is None else float(bench)
        record["week"] = int(record.get("week") or 0)
        record["team_id"] = int(record.get("team_id") or 0)
        record["owner"] = record.get("owner") or ""
        record["roster"] = record.get("roster") or []
        records.append(record)

    df = pd.DataFrame.from_records(records)
    df = df.sort_values(["week", "team_id"]).reset_index(drop=True)
    return df


def _expand_lineup_slots(slot_counts: Dict[str, int]) -> List[str]:
    slots: List[str] = []
    for slot, count in slot_counts.items():
        if slot in {"BE", "BN", "IR", "TAXI"}:
            continue
        slots.extend([slot] * int(count))
    return slots


def _slot_allows(slot: str, eligible_slots: Sequence[str]) -> bool:
    if slot in eligible_slots:
        return True
    if "/" in slot:
        allowed = set(part.strip() for part in slot.split("/") if part)
        return any(part in eligible_slots for part in allowed)
    if slot == "OP":
        return any(pos in eligible_slots for pos in {"QB", "RB", "WR", "TE", "TQB"})
    if slot == "ER":
        return any(pos in eligible_slots for pos in {"RB", "WR", "TE"})
    return False


def _optimal_lineup_score(roster: Iterable[Dict[str, Any]], slots: List[str]) -> float:
    players = [player for player in roster if player]
    if not players or not slots:
        return 0.0

    points = [float(p.get("points") or 0.0) for p in players]
    eligibility = [list(p.get("eligible_slots") or []) for p in players]

    from functools import lru_cache

    total_slots = len(slots)
    total_players = len(players)

    @lru_cache(maxsize=None)
    def _best(slot_idx: int, used_mask: int) -> float:
        if slot_idx >= total_slots:
            return 0.0

        best = 0.0
        slot = slots[slot_idx]
        # Option to leave the slot empty if no eligible players remain.
        best = _best(slot_idx + 1, used_mask)
        for player_idx in range(total_players):
            if used_mask & (1 << player_idx):
                continue
            if not _slot_allows(slot, eligibility[player_idx]):
                continue
            candidate = points[player_idx] + _best(slot_idx + 1, used_mask | (1 << player_idx))
            if candidate > best:
                best = candidate
        return best

    return float(round(_best(0, 0), 2))


def compute_optimal_points(
    roster: Iterable[Dict[str, Any]],
    league_rules: Dict[str, Any],
    *,
    actual_points: float = 0.0,
) -> float:
    """Return the optimal lineup total for a roster using league slot rules."""

    slot_counts = dict(league_rules.get("slot_counts") or {})
    slots = _expand_lineup_slots(slot_counts)
    if not slots:
        return float(actual_points)
    return _optimal_lineup_score(roster, slots)


def add_optimal_points(df: pd.DataFrame, league_rules: Dict[str, Any]) -> pd.DataFrame:
    """Append ``optimal_points`` and ``efficiency`` columns to the DataFrame."""

    slot_counts = dict(league_rules.get("slot_counts") or {})
    slots = _expand_lineup_slots(slot_counts)
    if not slots:
        df = df.copy()
        df["optimal_points"] = df["points"]
        df["efficiency"] = 1.0
        return df

    optimal_scores: List[float] = []
    for _, row in df.iterrows():
        roster = row.get("roster") or []
        optimal = _optimal_lineup_score(roster, slots)
        optimal_scores.append(optimal)

    df = df.copy()
    df["optimal_points"] = optimal_scores
    df["efficiency"] = df.apply(
        lambda r: (r["points"] / r["optimal_points"]) if r["optimal_points"] else 0.0,
        axis=1,
    )
    return df
