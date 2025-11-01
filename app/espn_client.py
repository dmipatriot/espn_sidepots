from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

import requests

from espn_api.football.constant import POSITION_MAP
from espn_api.football.league import League

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

BENCH_SLOTS = {"BE", "BN", "IR", "TAXI"}


def _ensure_browser_user_agent() -> None:
    """Force requests to report a desktop browser user agent."""

    requests.utils.default_user_agent = lambda: BROWSER_USER_AGENT


def _preflight_league_request(league_id: int, season: int, espn_s2: str, swid: str) -> None:
    """Perform a preflight GET request to detect ESPN 403s early."""

    url = (
        "https://fantasy.espn.com/apis/v3/games/ffl/seasons/"
        f"{season}/segments/0/leagues/{league_id}"
    )
    response = requests.get(
        url,
        params={"view": "mSettings"},
        cookies={"SWID": swid, "espn_s2": espn_s2},
        headers={"User-Agent": BROWSER_USER_AGENT},
        timeout=20,
    )
    if response.status_code != 200:
        msg = (
            "ESPN league preflight failed with status "
            f"{response.status_code}: {response.text.strip()}"
        )
        raise RuntimeError(msg)

@dataclass(frozen=True)
class TeamWeekScore:
    team_id: int
    owner: str
    week: int
    points: float
    bench_points: float | None = None
    roster: List[Dict[str, Any]] | None = None
    raw: Dict[str, Any] | None = None

def get_league(league_id: int, season: int, espn_s2: str, swid: str):
    """Instantiate and return an ``espn_api.football.League`` object."""

    _ensure_browser_user_agent()
    _preflight_league_request(league_id, season, espn_s2, swid)

    return League(
        league_id=league_id,
        year=season,
        espn_s2=espn_s2,
        swid=swid,
    )

def get_weeks(weeks_spec: str, regular_season_weeks: int, last_completed: int | None = None) -> List[int]:
    """Parse the CLI week specifier into a sorted list of week numbers."""

    spec = weeks_spec.strip().lower()
    if spec == "auto":
        upper = last_completed or regular_season_weeks
        upper = min(max(upper, 1), regular_season_weeks)
        return list(range(1, upper + 1))

    def _validate(values: Iterable[int]) -> List[int]:
        weeks = sorted({week for week in values if 1 <= week <= regular_season_weeks})
        if not weeks:
            msg = f"No valid weeks parsed from '{weeks_spec}'."
            raise ValueError(msg)
        return weeks

    if "," in spec:
        parts = [int(part.strip()) for part in spec.split(",") if part.strip()]
        return _validate(parts)

    if "-" in spec:
        start_str, end_str = spec.split("-", 1)
        start = int(start_str.strip())
        end = int(end_str.strip())
        if start > end:
            start, end = end, start
        return _validate(range(start, end + 1))

    week = int(spec)
    return _validate([week])

def fetch_week_scores(league, week: int) -> List[TeamWeekScore]:
    """Return per-team scoring for a specific week using ``league.box_scores``."""

    results: List[TeamWeekScore] = []
    for box_score in league.box_scores(week):
        for side in ("home", "away"):
            team = getattr(box_score, f"{side}_team")
            if not team:
                continue

            lineup = list(getattr(box_score, f"{side}_lineup", []) or [])
            roster: List[Dict[str, Any]] = []
            bench_total = 0.0
            for player in lineup:
                slot = getattr(player, "slot_position", "")
                points = float(getattr(player, "points", 0.0) or 0.0)
                eligible = list(getattr(player, "eligibleSlots", []) or [])
                roster.append(
                    {
                        "name": getattr(player, "name", "Unknown"),
                        "points": points,
                        "slot": slot,
                        "eligible_slots": eligible,
                        "position": getattr(player, "position", slot),
                    }
                )
                if slot in BENCH_SLOTS:
                    bench_total += points

            results.append(
                TeamWeekScore(
                    team_id=team.team_id,
                    owner=getattr(team, "owner", getattr(team, "team_name", "")),
                    week=week,
                    points=float(getattr(box_score, f"{side}_score", 0.0) or 0.0),
                    bench_points=bench_total,
                    roster=roster,
                    raw={"box_score_side": side},
                )
            )
    return results

def last_completed_week(league) -> int:
    """Return last regular-season week with a resolved matchup."""

    data = league.espn_request.get_league()
    schedule = data.get("schedule", [])
    completion: Dict[int, bool] = {}
    for matchup in schedule:
        week = int(matchup.get("matchupPeriodId", 0) or 0)
        if week <= 0:
            continue
        if matchup.get("winner") == "UNDECIDED":
            completion[week] = False
        else:
            completion.setdefault(week, True)

    regular_weeks = int(
        data.get("settings", {})
        .get("scheduleSettings", {})
        .get("matchupPeriodCount", getattr(league.settings, "reg_season_count", 0))
    )
    completed_weeks = [
        week for week, is_done in completion.items() if week <= regular_weeks and is_done
    ]
    if not completed_weeks:
        return 0
    return max(completed_weeks)


def extract_league_rules(league) -> Dict[str, Any]:
    """Return the roster slot configuration for the supplied league."""

    data = league.espn_request.get_league()
    roster_settings = data.get("settings", {}).get("rosterSettings", {})
    slot_counts_raw = roster_settings.get("lineupSlotCounts", {}) or {}
    slot_counts: Dict[str, int] = {}
    for slot_id, count in slot_counts_raw.items():
        try:
            slot_name = POSITION_MAP[int(slot_id)]
        except (TypeError, ValueError, KeyError):
            slot_name = str(slot_id)
        slot_counts[slot_name] = int(count)

    return {
        "slot_counts": slot_counts,
        "regular_season_weeks": int(
            data.get("settings", {})
            .get("scheduleSettings", {})
            .get("matchupPeriodCount", getattr(league.settings, "reg_season_count", 0))
        ),
    }
