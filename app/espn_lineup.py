"""Helpers for lineup-based optimal scoring derived from weekly box scores."""
from __future__ import annotations

from typing import Iterable, List, Sequence, Set, Tuple

STARTER_EXCLUDES = {"BE", "BN", "BENCH", "IR", "RES", "INJ"}
FLEX_LABELS = {"RB/WR/TE"}
SUPERFLEX_LABELS = {"OP"}


def _pos(value) -> str:
    """Return a normalized position label for lineup/eligibility strings."""

    if value is None:
        return ""
    if hasattr(value, "position"):
        raw = getattr(value, "position")
    else:
        raw = value
    text = str(raw or "").strip().upper()
    if not text:
        return ""
    # Remove whitespace for consistent comparisons.
    text = text.replace(" ", "")
    if text in {"D/ST", "DST", "D", "DEF", "DST/DEF"}:
        return "DST"
    if "DST" in text or "DEF" in text:
        return "DST"
    return text


def _eligible_from_label(label: str) -> Set[str]:
    label = (label or "").upper()
    if not label:
        return set()
    if label in FLEX_LABELS:
        return {"RB", "WR", "TE"}
    if label in SUPERFLEX_LABELS:
        return {"QB", "RB", "WR", "TE"}
    if "/" in label:
        return {_pos(part) for part in label.split("/") if part}
    return {_pos(label)}


def build_slot_plan_from_lineup(players: Sequence[object]) -> Tuple[dict[str, int], List[Set[str]]]:
    """Return the fixed-slot counts and flex slot eligibility for a lineup."""

    fixed: dict[str, int] = {}
    flex: List[Set[str]] = []
    for player in players:
        slot = _pos(getattr(player, "slot_position", ""))
        if not slot:
            continue
        if slot in STARTER_EXCLUDES:
            continue
        if slot in FLEX_LABELS:
            flex.append({"RB", "WR", "TE"})
            continue
        if slot in SUPERFLEX_LABELS:
            flex.append({"QB", "RB", "WR", "TE"})
            continue
        fixed[slot] = fixed.get(slot, 0) + 1
    return fixed, flex


def sum_points_for_slots(players: Iterable[object], include_labels: Iterable[str]) -> float:
    labels = {str(label or "").upper() for label in include_labels}
    total = 0.0
    if not labels:
        return total
    for player in players:
        slot = str(getattr(player, "slot_position", "") or "").upper()
        if slot not in labels:
            continue
        total += float(getattr(player, "points", 0.0) or 0.0)
    return float(total)


def _best_by_position(players: Sequence[object], position: str, used_ids: Set[int]) -> List[Tuple[object, float]]:
    candidates: List[Tuple[object, float]] = []
    for player in players:
        pid = id(player)
        if pid in used_ids:
            continue
        pos = _pos(getattr(player, "position", None) or getattr(player, "slot_position", ""))
        if pos != position:
            continue
        points = float(getattr(player, "points", 0.0) or 0.0)
        candidates.append((player, points))
    candidates.sort(key=lambda item: item[1], reverse=True)
    return candidates


def _eligible_candidates(
    players: Sequence[object], allowed: Set[str], used_ids: Set[int]
) -> List[Tuple[object, float]]:
    allowed_norm = {_pos(label) for label in allowed}
    candidates: List[Tuple[object, float]] = []
    for player in players:
        pid = id(player)
        if pid in used_ids:
            continue
        position = _pos(getattr(player, "position", None) or getattr(player, "slot_position", ""))
        if position not in allowed_norm:
            continue
        points = float(getattr(player, "points", 0.0) or 0.0)
        candidates.append((player, points))
    candidates.sort(key=lambda item: item[1], reverse=True)
    return candidates


def compute_optimal_with_assignment(
    players: Sequence[object], fixed: dict[str, int], flex: Sequence[Set[str]]
) -> Tuple[float, List[Tuple[str, str, float]]]:
    """Compute a greedy optimal lineup using the provided weekly roster."""

    used_ids: Set[int] = set()
    assignment: List[Tuple[str, str, float]] = []
    total = 0.0

    for position, count in fixed.items():
        candidates = _best_by_position(players, position, used_ids)
        for player, points in candidates[:count]:
            pid = id(player)
            if pid in used_ids:
                continue
            used_ids.add(pid)
            total += points
            assignment.append((position, getattr(player, "name", ""), points))

    for allowed in flex:
        candidates = _eligible_candidates(players, allowed, used_ids)
        if not candidates:
            continue
        player, points = candidates[0]
        pid = id(player)
        if pid in used_ids:
            continue
        used_ids.add(pid)
        total += points
        slot_label = "/".join(sorted(allowed))
        assignment.append((slot_label, getattr(player, "name", ""), points))

    return float(total), assignment


def format_lines(assign_list: Sequence[Tuple[str, str, float]]) -> str:
    """Return a newline-delimited string describing an assignment list."""

    return "\n".join(f"{slot}: {name} ({points:.2f})" for slot, name, points in assign_list)
