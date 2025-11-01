from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

import yaml

from app import discord
from app.efficiency import EffStat, format_efficiency_table, update_efficiency
from app.espn_client import (
    ESPNClient,
    build_member_display_map,
    build_team_label_map,
    extract_league_rules,
    fetch_settings,
    fetch_teams,
    fetch_week_scores,
    get_weeks,
    init_league,
    label_for,
    last_completed_week,
    preflight_league,
)
from app.pir import compute_pir
from app.scoring import add_optimal_points, build_base_frame
from app.survivor import run_survivor


_LOG_LEVEL_NAME = os.getenv("LOG_LEVEL", "INFO").upper()
_LEVEL_MAPPING = logging.getLevelNamesMapping()
_LOG_LEVEL = _LEVEL_MAPPING.get(_LOG_LEVEL_NAME, logging.INFO)
logging.basicConfig(level=_LOG_LEVEL, format="%(asctime)s %(levelname)s %(message)s")
LOGGER = logging.getLogger("espn_sidepots")

LOCK_PATH = Path("/tmp/espn_sidepots.lock")
LOCK_MAX_AGE_SECONDS = 300


def load_config() -> Dict[str, object]:
    """Load the league configuration file."""

    with open(Path(__file__).parents[1] / "config" / "league.yaml", "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["pir", "efficiency", "survivor", "all"], default="all")
    parser.add_argument("--weeks", default="auto", help="auto | N | A-B | A,B,C")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def _format_pir_summary(result: Dict[str, object], labels: Dict[int, str]) -> List[str]:
    leaderboard = result["leaderboard_df"].head(5)
    lines = []
    for _, row in leaderboard.iterrows():
        team_label = label_for(int(row["team_id"]), labels)
        lines.append(
            f"Week {int(row['week'])}: {team_label} - {row['points']:.2f} (Δ {row['delta']:.2f})"
        )
    return lines or ["No qualifying scores"]


def _format_survivor_summary(
    result: Dict[str, object], labels: Dict[int, str], last_completed_week: int | None
) -> List[str]:
    lines: List[str] = list(result.get("summary", []))
    display = lines[:5]
    if last_completed_week is not None:
        target_prefix = f"Week {last_completed_week}:"
        latest_line = next(
            (line for line in reversed(lines) if line.startswith(target_prefix)),
            None,
        )
        if latest_line and latest_line not in display:
            if len(display) >= 5:
                display[-1] = latest_line
            else:
                display.append(latest_line)

    alive = result.get("alive", [])
    if alive:
        alive_labels = [label_for(int(team), labels) for team in alive]
        display.append("Alive: " + ", ".join(alive_labels))
    return display or ["No eliminations yet"]


def _format_weeks_for_log(weeks: List[int]) -> str:
    return ",".join(str(week) for week in weeks) if weeks else "none"


def _maybe_post(
    cfg: Dict[str, object], key: str, title: str, lines: List[str], dry_run: bool
) -> bool:
    if dry_run:
        LOGGER.info("Dry-run: skipping Discord post for %s", title)
        print(f"\n[{title}]")
        for line in lines:
            print(line)
        return False

    LOGGER.info("Posting %s report to Discord", title)
    status = discord.post_text(cfg, key, title, lines)
    if status is None:
        LOGGER.info("Discord webhook for %s not configured; skipping", title)
        return False

    LOGGER.info("Discord post for %s completed with status=%s", title, status)
    return 200 <= int(status) < 300


def _get_int_env(name: str, default: int | None) -> int:
    value = os.getenv(name)
    if value:
        try:
            return int(value)
        except ValueError:
            LOGGER.warning("Invalid integer for %s environment override; falling back to config", name)
    if default is None:
        raise RuntimeError(f"Missing configuration for {name}")
    return int(default)


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    tail = value[-6:]
    return f"*...{tail}"


def _acquire_lock() -> bool:
    now = time.time()
    try:
        if LOCK_PATH.exists():
            age = now - LOCK_PATH.stat().st_mtime
            if age < LOCK_MAX_AGE_SECONDS:
                LOGGER.info("lock present, skipping (age=%.1fs)", age)
                return False
    except FileNotFoundError:  # pragma: no cover - race on deletion
        pass

    LOCK_PATH.write_text(str(int(now)))
    return True


def main() -> None:
    """Entry point for the CLI application."""

    cfg = load_config()
    args = parse_args()

    LOGGER.info("Starting run mode=%s weeks=%s dry_run=%s", args.mode, args.weeks, args.dry_run)

    lock_acquired = _acquire_lock()
    if not lock_acquired:
        return

    post_statuses: List[bool] = []

    try:
        league_id = _get_int_env("LEAGUE_ID", cfg.get("league_id"))
        season = _get_int_env("SEASON", cfg.get("season"))
        espn_s2 = os.getenv("ESPN_S2") or cfg.get("espn_s2", "")
        swid = os.getenv("SWID") or cfg.get("swid", "")

        LOGGER.info(
            "Starting run mode=%s weeks=%s league_id=%s season=%s",
            args.mode,
            args.weeks,
            league_id,
            season,
        )

        LOGGER.info(
            "Credentials: league_id=%s season=%s espn_s2=%s swid=%s",
            league_id,
            season,
            _mask_secret(espn_s2),
            _mask_secret(swid),
        )

        client = ESPNClient(
            league_id=league_id,
            season=season,
            espn_s2=espn_s2,
            swid=swid,
        )

        preflight_league(
            league_id=league_id,
            season=season,
            espn_s2=espn_s2,
            swid=swid,
        )
        LOGGER.info("[preflight] OK (JSON)")

        settings_payload = fetch_settings(client)
        teams_payload = fetch_teams(client)
        member_map = build_member_display_map(settings_payload)
        labels = build_team_label_map(
            teams_payload,
            member_map,
            include_owner=True,
        )
        rules = extract_league_rules(client, settings_payload)
        regular_weeks = int(
            cfg.get("regular_season_weeks") or rules.get("regular_season_weeks") or 0
        )
        league = init_league(client)
        lcw = last_completed_week(client, start_week=1)
        weeks = get_weeks(args.weeks, regular_weeks, last_completed=lcw)

        payload: List[Dict[str, object]] = []
        stats: Dict[int, EffStat] = {}
        dedupe_seen: Set[Tuple[int, int]] = set()
        modes = [args.mode] if args.mode != "all" else ["pir", "efficiency", "survivor"]
        weeks = sorted(set(weeks))
        weeks = [week for week in weeks if week <= lcw]
        weeks_label = _format_weeks_for_log(weeks)
        need_payload = any(mode in modes for mode in ("pir", "survivor"))

        for week in weeks:
            week_scores = fetch_week_scores(league, week)
            week_payload = [asdict(team_score) for team_score in week_scores]
            if need_payload:
                payload.extend(week_payload)

            if "efficiency" in modes:
                update_efficiency(stats, week_scores, seen=dedupe_seen)

        scoring_df = None
        if need_payload:
            base_df = build_base_frame(payload)
            scoring_df = add_optimal_points(base_df, rules)

        if "pir" in modes:
            LOGGER.info("Starting PIR report for weeks=%s", weeks_label)
            if scoring_df is None:
                base_df = build_base_frame([])
                scoring_df = add_optimal_points(base_df, rules)
            pir_result = compute_pir(
                scoring_df,
                target=float(cfg.get("pir_target", 150.0)),
                tiebreaks=list((cfg.get("tiebreaks") or {}).get("pir", [])),
                weeks_scope=weeks,
                labels=labels,
            )
            posted = _maybe_post(
                cfg,
                "pir",
                "Price Is Right",
                _format_pir_summary(pir_result, labels),
                args.dry_run,
            )
            if posted:
                post_statuses.append(posted)

        if "efficiency" in modes:
            LOGGER.info("Starting efficiency report for weeks=%s", weeks_label)
            report_text = format_efficiency_table(labels, stats)
            report_lines = report_text.splitlines()
            posted = _maybe_post(
                cfg,
                "efficiency",
                "Season Efficiency",
                report_lines,
                args.dry_run,
            )
            if posted:
                post_statuses.append(posted)

        if "survivor" in modes:
            LOGGER.info("Starting survivor report for weeks=%s", weeks_label)
            survivor_result = run_survivor(
                scoring_df,
                start_week=int(cfg.get("survivor_start_week", 1)),
                tiebreaks=list((cfg.get("tiebreaks") or {}).get("survivor", [])),
                weeks_scope=weeks,
                last_completed_week=lcw,
                labels=labels,
            )
            posted = _maybe_post(
                cfg,
                "survivor",
                "Survivor Pool",
                _format_survivor_summary(survivor_result, labels, lcw),
                args.dry_run,
            )
            if posted:
                post_statuses.append(posted)

        LOGGER.info("Done.")
    finally:
        if lock_acquired:
            try:
                LOCK_PATH.unlink()
            except FileNotFoundError:  # pragma: no cover - already removed
                pass

    if len(post_statuses) == 3 and all(post_statuses):
        LOGGER.info("✅ All reports posted successfully. Exiting 0")
        sys.exit(0)


if __name__ == "__main__":
    main()
