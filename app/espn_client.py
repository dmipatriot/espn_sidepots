from __future__ import annotations

import os
import time
from dataclasses import dataclass
from json import JSONDecodeError
from typing import Any, Dict, Iterable, List

import logging

import requests

from espn_api.football.constant import POSITION_MAP

from app.espn_lineup import (
    STARTER_EXCLUDES,
    build_slot_plan_from_lineup,
    compute_optimal_with_assignment,
    sum_points_for_slots,
    _pos,
)

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

LOGGER = logging.getLogger(__name__)

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
                        LOGGER.debug(
                            "[http] ok host=%s status=%s", host_label, response.status_code
                        )
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
    optimal_points: float = 0.0


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


def build_member_display_map(settings_json: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in settings_json.get("members", []):
        mid = str(m.get("id") or m.get("memberId") or "")
        if not mid:
            continue
        dn = (m.get("displayName") or "").strip()
        fn = (m.get("firstName") or "").strip()
        ln = (m.get("lastName") or "").strip()
        alt = (m.get("alternateId") or "").strip()
        if dn:
            out[mid] = dn
        elif fn or ln:
            out[mid] = (f"{fn} {ln}").strip()
        elif alt:
            out[mid] = alt
        else:
            out[mid] = mid[:6].upper()
    return out


def build_team_label_map(
    teams_json: dict,
    member_map: dict[str, str],
    *,
    include_owner: bool = True,
) -> dict[int, str]:
    """
    Build {team_id: 'Location Nickname (Owner)'} robustly from mTeam.
    Priority:
      1) f"{location} {nickname}".strip() if either exists
      2) team.get('name')  (some leagues set a single name)
      3) f"Team {id}"
    Owner:
      - Use first of team.get('owners', []) or team.get('primaryOwner')
      - Map via member_map to a readable display
    Never use 'abbrev' unless EVERYTHING else is missing.
    """

    labels: dict[int, str] = {}
    for t in teams_json.get("teams", []):
        tid_raw = t.get("id") if t.get("id") is not None else t.get("teamId")
        if tid_raw is None:
            continue
        try:
            tid = int(tid_raw)
        except (TypeError, ValueError):
            continue

        loc = (t.get("location") or t.get("teamLocation") or "").strip()
        nick = (t.get("nickname") or t.get("teamNickname") or "").strip()
        name = (t.get("name") or "").strip()
        owner_id = ""
        owners = t.get("owners") or []
        if isinstance(owners, list) and owners:
            owner_id = str(owners[0])
        if not owner_id:
            owner_id = str(t.get("primaryOwner") or "")
        owner_disp = member_map.get(owner_id, "").strip()

        if loc or nick:
            base = f"{loc} {nick}".strip()
        elif name:
            base = name
        else:
            base = f"Team {tid}"

        label = base
        if include_owner and owner_disp:
            label = f"{base} ({owner_disp})"

        labels[tid] = label
    return labels


def label_for(team_id: int, labels: Dict[int, str]) -> str:
    """Return a human-friendly label for a team identifier."""

    try:
        normalized_id = int(team_id)
    except (TypeError, ValueError):
        return str(team_id)

    if normalized_id in labels and labels[normalized_id]:
        return labels[normalized_id]
    return f"Team {normalized_id}"


def fetch_week_matchups(client: ESPNClient, week: int) -> Dict[str, Any]:
    cookies = _apply_client_context(client)
    params = {"view": "mMatchup", "scoringPeriodId": int(week)}
    return _json_get("", params=params, cookies=cookies, retries=1)


def is_week_complete(matchups_json: dict) -> bool:
    """Return ``True`` when all matchups for the scoring period have a winner."""

    schedule = matchups_json.get("schedule") or []
    if not schedule:
        return False

    raw_period = matchups_json.get("scoringPeriodId")
    try:
        scoring_period = int(raw_period)
    except (TypeError, ValueError):
        scoring_period = None

    relevant_matchups: List[Dict[str, Any]] = []
    for matchup in schedule:
        matchup_period = matchup.get("matchupPeriodId")
        try:
            matchup_period_int = int(matchup_period)
        except (TypeError, ValueError):
            matchup_period_int = None

        if scoring_period is not None and matchup_period_int not in (None, scoring_period):
            continue

        relevant_matchups.append(matchup)

    if not relevant_matchups:
        relevant_matchups = schedule

    for matchup in relevant_matchups:
        winner = (matchup.get("winner") or "").strip().upper()
        if winner not in {"HOME", "AWAY", "TIE"}:
            return False

    return True


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


class _JSONPlayer:
    """Lightweight object to satisfy lineup helper expectations."""

    def __init__(
        self,
        *,
        name: str,
        slot_label: str,
        points: float,
        position: str,
        eligible: Iterable[str],
    ) -> None:
        self.name = name
        self.slot_position = slot_label
        self.points = float(points or 0.0)
        self.position = position
        self.eligibleSlots = list(eligible)


def _slot_label(slot_id: Any) -> str:
    if slot_id is None:
        return ""
    if slot_id in POSITION_MAP:
        return str(POSITION_MAP[slot_id] or "").upper()
    try:
        value = int(slot_id)
    except (TypeError, ValueError):
        return str(slot_id).upper()
    return str(POSITION_MAP.get(value, value)).upper()


def _position_label(position_id: Any, fallback: str = "") -> str:
    if position_id is None:
        return _pos(fallback)
    if position_id in POSITION_MAP:
        return _pos(POSITION_MAP[position_id])
    try:
        value = int(position_id)
    except (TypeError, ValueError):
        return _pos(position_id)
    return _pos(POSITION_MAP.get(value, value))


def _eligible_labels(raw: Iterable[Any]) -> List[str]:
    labels: List[str] = []
    for item in raw or []:
        labels.append(_slot_label(item))
    return [label for label in labels if label]


def _player_points(entry: Dict[str, Any], scoring_period: int) -> float:
    direct_fields = [
        entry.get("appliedStatTotal"),
        entry.get("appliedTotal"),
        entry.get("pAppliedStatTotal"),
        entry.get("pAppliedTotal"),
    ]
    for value in direct_fields:
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                continue

    stats_candidates: List[Dict[str, Any]] = []
    player_entry = entry.get("playerPoolEntry", {}) or {}
    player = player_entry.get("player", {}) or {}
    stats_candidates.extend(player_entry.get("stats", []) or [])
    stats_candidates.extend(player.get("stats", []) or [])
    stats_candidates.extend(entry.get("playerStats", []) or [])

    chosen: List[Dict[str, Any]] = []
    for stat in stats_candidates:
        try:
            period = int(stat.get("scoringPeriodId"))
        except (TypeError, ValueError):
            period = None
        if period is not None and period != scoring_period:
            continue
        chosen.append(stat)

    # Prefer actual scoring (statSourceId == 0) over projections.
    chosen.sort(key=lambda item: int(item.get("statSourceId", 99)))
    for stat in chosen:
        for key in ("appliedTotal", "appliedStatTotal", "points"):
            value = stat.get(key)
            if value is None:
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue

    return 0.0


def _player_name(player_payload: Dict[str, Any]) -> str:
    name_fields = [
        player_payload.get("fullName"),
        player_payload.get("firstName"),
        player_payload.get("lastName"),
        player_payload.get("displayName"),
    ]
    for value in name_fields:
        if value:
            return str(value)
    return ""


def _team_owner_fallback(team_payload: Dict[str, Any], team_id: int) -> str:
    nickname = (team_payload.get("nickname") or team_payload.get("teamNickname") or "").strip()
    location = (team_payload.get("location") or team_payload.get("teamLocation") or "").strip()
    if nickname and location:
        return f"{location} {nickname}".strip()
    if nickname:
        return nickname
    if location:
        return location
    return f"Team {team_id}"


def fetch_week_scores(client: ESPNClient, week: int) -> List[TeamWeekScore]:
    """Return per-team scoring for a specific week using only JSON payloads."""

    matchups_payload = fetch_week_matchups(client, week)
    rosters_payload = fetch_week_rosters(client, week)

    try:
        scoring_period = int(matchups_payload.get("scoringPeriodId", week))
    except (TypeError, ValueError):
        scoring_period = int(week)

    aggregated: Dict[int, Dict[str, Any]] = {}

    for matchup in matchups_payload.get("schedule", []) or []:
        for side in ("home", "away"):
            team_blob = matchup.get(side) or {}
            team_id = team_blob.get("teamId")
            if team_id is None:
                continue
            try:
                tid = int(team_id)
            except (TypeError, ValueError):
                continue

            record = aggregated.setdefault(tid, {"players": [], "roster": [], "owner": ""})
            total_points = team_blob.get("totalPoints")
            if total_points is None:
                total_points = team_blob.get("totalPointsLive")
            if total_points is None:
                total_points = team_blob.get("score")
            if total_points is not None:
                try:
                    record["score"] = float(total_points)
                except (TypeError, ValueError):
                    record["score"] = 0.0
            if not record.get("owner"):
                record["owner"] = _team_owner_fallback(team_blob, tid)

    teams_payload = rosters_payload.get("teams", []) or []
    for team_payload in teams_payload:
        tid_raw = team_payload.get("id")
        if tid_raw is None:
            tid_raw = team_payload.get("teamId")
        if tid_raw is None:
            continue
        try:
            tid = int(tid_raw)
        except (TypeError, ValueError):
            continue

        record = aggregated.setdefault(tid, {"players": [], "roster": [], "owner": ""})
        if not record.get("owner"):
            record["owner"] = _team_owner_fallback(team_payload, tid)

        roster_entries = team_payload.get("roster", {}).get("entries", []) or []
        for entry in roster_entries:
            slot_label = _slot_label(entry.get("lineupSlotId"))
            player_entry = entry.get("playerPoolEntry", {}) or {}
            player_payload = player_entry.get("player", {}) or {}
            name = _player_name(player_payload)
            eligible = _eligible_labels(player_payload.get("eligibleSlots", []) or [])
            if not eligible:
                default_pos = player_payload.get("defaultPositionId")
                fallback = _position_label(default_pos)
                if fallback:
                    eligible = [fallback]
            position = _position_label(player_payload.get("defaultPositionId"), slot_label)
            points = _player_points(entry, scoring_period)

            player_obj = _JSONPlayer(
                name=name,
                slot_label=slot_label,
                points=points,
                position=position,
                eligible=eligible,
            )
            record.setdefault("players", []).append(player_obj)
            record.setdefault("roster", []).append(
                {
                    "name": name,
                    "points": float(points),
                    "slot": slot_label,
                    "eligible_slots": list(eligible),
                    "position": position,
                }
            )

    results: List[TeamWeekScore] = []
    for team_id, record in aggregated.items():
        players = record.get("players", [])
        starter_labels = {
            str(getattr(player, "slot_position", "") or "").upper()
            for player in players
            if str(getattr(player, "slot_position", "") or "").upper()
            and str(getattr(player, "slot_position", "") or "").upper() not in STARTER_EXCLUDES
        }
        actual_points = sum_points_for_slots(players, starter_labels)
        fixed, flex = build_slot_plan_from_lineup(players)
        optimal_points, _ = compute_optimal_with_assignment(players, fixed, flex)
        bench_points = sum_points_for_slots(players, STARTER_EXCLUDES)

        results.append(
            TeamWeekScore(
                team_id=team_id,
                owner=str(record.get("owner") or f"Team {team_id}"),
                week=int(week),
                points=float(actual_points or 0.0),
                bench_points=float(bench_points) if bench_points is not None else None,
                roster=list(record.get("roster", [])),
                raw={"score": record.get("score", 0.0)},
                optimal_points=float(optimal_points or 0.0),
            )
        )

    results.sort(key=lambda item: item.team_id)
    return results


def last_completed_week(
    client: ESPNClient, *, start_week: int = 1, end_week: int | None = None
) -> int:
    """Return the most recent week with a decided matchup winner."""

    settings = fetch_settings(client)
    schedule_settings = (
        settings.get("settings", {}).get("scheduleSettings", {}) or {}
    )
    regular_weeks = int(schedule_settings.get("matchupPeriodCount") or 0)

    status = settings.get("status", {}) or {}
    status_candidates: List[int] = []
    for key in (
        "latestScoringPeriod",
        "currentScoringPeriod",
        "finalScoringPeriod",
        "finalScoringPeriodId",
    ):
        value = status.get(key)
        try:
            status_candidates.append(int(value))
        except (TypeError, ValueError):
            continue

    if end_week is not None:
        try:
            upper_bound = int(end_week)
        except (TypeError, ValueError):
            upper_bound = start_week - 1
    elif regular_weeks:
        upper_bound = regular_weeks
    elif status_candidates:
        upper_bound = max(status_candidates)
    else:
        upper_bound = start_week - 1

    if regular_weeks:
        upper_bound = min(max(upper_bound, 0), regular_weeks)

    if upper_bound < start_week:
        return start_week - 1

    last_complete = start_week - 1
    for week in range(start_week, upper_bound + 1):
        matchups_payload = fetch_week_matchups(client, week)
        if is_week_complete(matchups_payload):
            last_complete = week
        else:
            break

    return last_complete


def extract_league_rules(
    client: ESPNClient, settings_payload: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    """Return the roster slot configuration for the supplied league."""

    settings = settings_payload or fetch_settings(client)
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
