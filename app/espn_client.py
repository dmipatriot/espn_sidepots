from __future__ import annotations
import os
import time
from dataclasses import dataclass
from json import JSONDecodeError
from typing import Any, Dict, Iterable, List

import requests

from espn_api.football.constant import POSITION_MAP
from espn_api.football.league import League

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://fantasy.espn.com/",
    "Origin": "https://fantasy.espn.com",
    "Cache-Control": "no-cache",
}

_SESSION = requests.Session()
_SESSION.headers.update(_DEFAULT_HEADERS)

_LEAGUE_CONTEXT: Dict[str, int] | None = None

_PRIMARY_HOST = ("fantasy", "https://fantasy.espn.com")
_ALT_HOST = ("lm-api-reads", "https://lm-api-reads.fantasy.espn.com")


def _set_league_context(league_id: int, season: int) -> None:
    """Store league context for subsequent HTTP requests."""

    global _LEAGUE_CONTEXT
    _LEAGUE_CONTEXT = {"league_id": int(league_id), "season": int(season)}


def _get_league_context() -> Dict[str, int]:
    if not _LEAGUE_CONTEXT:
        raise RuntimeError("League context not initialized; call preflight_league first")
    return _LEAGUE_CONTEXT


def _host_priority() -> List[tuple[str, str]]:
    use_alt_first = os.getenv("ESPN_USE_ALT_HOST") == "1"
    hosts = [_PRIMARY_HOST, _ALT_HOST]
    if use_alt_first:
        hosts = [hosts[1], hosts[0]]
    return hosts


def _normalize_path(path: str) -> str:
    if not path:
        return ""
    if path.startswith("/") or path.startswith("?"):
        return path
    return f"/{path}"


def _build_url(host: str, season: int, league_id: int, path: str) -> str:
    base = (
        f"{host}/apis/v3/games/ffl/seasons/{season}/segments/0/leagues/{league_id}"
    )
    return f"{base}{_normalize_path(path)}"


def _sanitize_body(body: str | None) -> str:
    if not body:
        return ""
    compact = " ".join(body.split())
    return compact[:200]

BENCH_SLOTS = {"BE", "BN", "IR", "TAXI"}


def _ensure_browser_user_agent() -> None:
    """Force requests to report a desktop browser user agent."""

    requests.utils.default_user_agent = lambda: _DEFAULT_HEADERS["User-Agent"]


def _json_get(
    path: str, params: Dict[str, Any], cookies: Dict[str, str], *, retries: int = 1
) -> Dict[str, Any]:
    """Fetch JSON from ESPN with retry, validation, and host failover."""

    context = _get_league_context()
    attempts = max(1, int(retries) + 1)
    query = dict(params or {})
    jar = dict(cookies or {})
    last_response: requests.Response | None = None
    last_error: Exception | None = None
    last_host_label = ""

    for host_label, host_base in _host_priority():
        url = _build_url(
            host_base,
            context["season"],
            context["league_id"],
            path,
        )
        last_host_label = host_label
        for attempt in range(attempts):
            try:
                response = _SESSION.get(
                    url,
                    params=query,
                    cookies=jar,
                    timeout=20,
                )
            except requests.RequestException as exc:  # pragma: no cover - network failure edge
                last_response = None
                last_error = exc
            else:
                last_response = response
                content_type = response.headers.get("Content-Type", "") or ""
                if response.status_code == 200 and "json" in content_type.lower():
                    try:
                        payload = response.json()
                    except (ValueError, JSONDecodeError) as exc:
                        last_error = exc
                    else:
                        print(f"[http] ok host={host_label} status={response.status_code}")
                        return payload
                else:
                    last_error = RuntimeError(
                        "Unexpected response "
                        f"(status={response.status_code}, content_type='{content_type}')"
                    )

            if attempt < attempts - 1:
                time.sleep(0.8)

        # retry on the next host

    status = "?"
    body = ""
    if last_response is not None:
        status = str(last_response.status_code)
        body = _sanitize_body(last_response.text)

    raise RuntimeError(
        f"ESPN API request failed (status={status} host={last_host_label}): {body}"
    ) from last_error


def preflight_league(league_id: int, season: int, espn_s2: str, swid: str) -> Dict[str, Any]:
    """Ensure ESPN league access returns JSON before using ``espn_api``."""

    _set_league_context(league_id, season)
    try:
        return _json_get(
            "",
            params={"view": "mSettings"},
            cookies={"SWID": swid, "espn_s2": espn_s2},
            retries=1,
        )
    except RuntimeError as exc:  # pragma: no cover - exercised in callers
        msg = (
            "ESPN league preflight failed. Verify LEAGUE_ID/SEASON and cookie secrets "
            "(SWID must include braces, ESPN_S2 must be current)."
        )
        raise RuntimeError(f"{msg} Details: {exc}") from exc

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

    _set_league_context(league_id, season)
    _ensure_browser_user_agent()

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
