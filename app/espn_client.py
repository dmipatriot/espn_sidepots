from __future__ import annotations

import os
import time
from dataclasses import dataclass
from json import JSONDecodeError
from typing import Any, Dict, Iterable, List

import requests

from espn_api.football.constant import POSITION_MAP

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
    """Ensure ESPN league access returns JSON before fetching additional data."""

    _set_league_context(league_id, season)
    _ensure_browser_user_agent()
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
class ESPNClient:
    league_id: int
    season: int
    espn_s2: str
    swid: str


@dataclass(frozen=True)
class TeamWeekScore:
    team_id: int
    owner: str
    week: int
    points: float
    bench_points: float | None = None
    roster: List[Dict[str, Any]] | None = None
    raw: Dict[str, Any] | None = None


def _apply_client_context(client: ESPNClient) -> Dict[str, str]:
    _set_league_context(client.league_id, client.season)
    _ensure_browser_user_agent()
    return {"SWID": client.swid, "espn_s2": client.espn_s2}


def fetch_settings(client: ESPNClient) -> Dict[str, Any]:
    cookies = _apply_client_context(client)
    return _json_get("", params={"view": "mSettings"}, cookies=cookies, retries=1)


def fetch_teams(client: ESPNClient) -> Dict[str, Any]:
    cookies = _apply_client_context(client)
    return _json_get("", params={"view": "mTeam"}, cookies=cookies, retries=1)


def fetch_week_matchups(client: ESPNClient, week: int) -> Dict[str, Any]:
    cookies = _apply_client_context(client)
    params = {"view": "mMatchup", "scoringPeriodId": int(week)}
    return _json_get("", params=params, cookies=cookies, retries=1)


def fetch_week_rosters(client: ESPNClient, week: int) -> Dict[str, Any]:
    cookies = _apply_client_context(client)
    params = {"view": "mRoster", "scoringPeriodId": int(week)}
    return _json_get("", params=params, cookies=cookies, retries=1)


def get_weeks(
    weeks_spec: str, regular_season_weeks: int, last_completed: int | None = None
) -> List[int]:
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


def fetch_week_scores(client: ESPNClient, week: int) -> List[TeamWeekScore]:
    """Return per-team scoring for a specific week using ESPN JSON endpoints."""

    teams_payload = fetch_teams(client)
    matchups_payload = fetch_week_matchups(client, week)
    rosters_payload = fetch_week_rosters(client, week)

    teams_by_id: Dict[int, Dict[str, Any]] = {}
    for team in teams_payload.get("teams", []) or []:
        team_id = team.get("teamId", team.get("id"))
        if team_id is None:
            continue
        teams_by_id[int(team_id)] = team

    roster_by_team: Dict[int, List[Dict[str, Any]]] = {}
    for roster_team in rosters_payload.get("teams", []) or []:
        team_id = roster_team.get("teamId", roster_team.get("id"))
        if team_id is None:
            continue
        entries = roster_team.get("roster", {}).get("entries", []) or []
        normalized_entries: List[Dict[str, Any]] = []
        for entry in entries:
            slot_id = entry.get("lineupSlotId")
            slot_name = POSITION_MAP.get(int(slot_id)) if slot_id is not None else None
            if slot_name is None:
                slot_name = str(slot_id)

            player_entry = entry.get("playerPoolEntry", {}) or {}
            player = player_entry.get("player", {}) or {}
            player_name = (
                player.get("fullName")
                or player.get("displayName")
                or player.get("firstName")
                or "Unknown"
            )

            eligible_raw = player.get("eligibleSlots") or player.get("eligiblePositions") or []
            eligible_slots = [
                POSITION_MAP.get(int(slot), str(slot)) for slot in eligible_raw
            ]

            position_id = player.get("defaultPositionId")
            position_name = (
                POSITION_MAP.get(int(position_id), str(position_id))
                if position_id is not None
                else slot_name
            )

            points_candidates = [
                entry.get("appliedStatTotal"),
                player_entry.get("appliedStatTotal"),
                entry.get("points"),
            ]
            points_value = 0.0
            for candidate in points_candidates:
                if candidate is not None:
                    points_value = float(candidate)
                    break

            normalized_entries.append(
                {
                    "name": player_name,
                    "points": points_value,
                    "slot": slot_name,
                    "eligible_slots": eligible_slots,
                    "position": position_name,
                }
            )
        roster_by_team[int(team_id)] = normalized_entries

    def _resolve_owner(team_id: int) -> str:
        team = teams_by_id.get(team_id, {})
        owners = team.get("owners") or []
        owner_display = ""
        if owners:
            owner = owners[0]
            if isinstance(owner, dict):
                owner_display = (
                    owner.get("displayName")
                    or " ".join(
                        part for part in [owner.get("firstName"), owner.get("lastName")] if part
                    )
                )
            else:
                owner_display = str(owner)

        if owner_display:
            return owner_display

        location = team.get("location", "").strip()
        nickname = team.get("nickname", "").strip()
        if location or nickname:
            return f"{location} {nickname}".strip()

        return f"Team {team_id}"

    results: List[TeamWeekScore] = []
    for matchup in matchups_payload.get("schedule", []) or []:
        matchup_week = int(matchup.get("matchupPeriodId", week) or week)
        if matchup_week != int(week):
            continue
        for side in ("home", "away"):
            team_info = matchup.get(side)
            if not team_info:
                continue
            team_id = team_info.get("teamId")
            if team_id is None:
                continue
            team_id = int(team_id)
            points = float(
                team_info.get("totalPoints")
                or team_info.get("points", 0.0)
                or 0.0
            )
            roster = roster_by_team.get(team_id)
            bench_points: float | None = None
            if roster is not None:
                bench_points = sum(
                    entry["points"] for entry in roster if entry["slot"] in BENCH_SLOTS
                )

            results.append(
                TeamWeekScore(
                    team_id=team_id,
                    owner=_resolve_owner(team_id),
                    week=int(week),
                    points=points,
                    bench_points=bench_points,
                    roster=roster,
                    raw={"matchup_id": matchup.get("id"), "side": side},
                )
            )

    return results


def last_completed_week(client: ESPNClient) -> int:
    """Return last completed scoring period for the league."""

    settings = fetch_settings(client)
    status = settings.get("status", {}) or {}
    latest = (
        status.get("latestScoringPeriod")
        or status.get("currentScoringPeriod")
        or status.get("finalScoringPeriod")
        or status.get("finalScoringPeriodId")
        or 0
    )
    try:
        latest_week = int(latest)
    except (TypeError, ValueError):
        latest_week = 0

    schedule_settings = (
        settings.get("settings", {}).get("scheduleSettings", {}) or {}
    )
    regular_weeks = int(schedule_settings.get("matchupPeriodCount") or 0)
    if regular_weeks:
        latest_week = min(latest_week, regular_weeks)

    return max(latest_week, 0)


def extract_league_rules(client: ESPNClient) -> Dict[str, Any]:
    """Return the roster slot configuration for the supplied league."""

    settings = fetch_settings(client)
    roster_settings = settings.get("settings", {}).get("rosterSettings", {}) or {}
    slot_counts_raw = roster_settings.get("lineupSlotCounts", {}) or {}
    slot_counts: Dict[str, int] = {}
    for slot_id, count in slot_counts_raw.items():
        try:
            slot_key = int(slot_id)
        except (TypeError, ValueError):
            slot_key = slot_id
        slot_name = POSITION_MAP.get(slot_key, str(slot_key))
        slot_counts[slot_name] = int(count)

    schedule_settings = (
        settings.get("settings", {}).get("scheduleSettings", {}) or {}
    )

    return {
        "slot_counts": slot_counts,
        "regular_season_weeks": int(schedule_settings.get("matchupPeriodCount") or 0),
    }
