from __future__ import annotations

import argparse
import os
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List

import yaml

from app import discord
from app.efficiency import season_efficiency
from app.espn_client import (
    extract_league_rules,
    fetch_week_scores,
    get_league,
    get_weeks,
    last_completed_week,
)
from app.pir import compute_pir
from app.scoring import add_optimal_points, build_base_frame
from app.survivor import run_survivor


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


def _format_pir_summary(result: Dict[str, object]) -> List[str]:
    leaderboard = result["leaderboard_df"].head(5)
    lines = []
    for _, row in leaderboard.iterrows():
        lines.append(
            f"Week {int(row['week'])}: {row['owner']} - {row['points']:.2f} (Δ {row['delta']:.2f})"
        )
    return lines or ["No qualifying scores"]


def _format_efficiency_summary(result: Dict[str, object]) -> List[str]:
    table = result["table"].head(5)
    lines = []
    for _, row in table.iterrows():
        lines.append(
            f"{row['owner']}: {row['season_efficiency']:.3f} (Pts {row['total_points']:.1f})"
        )
    return lines or ["No efficiency data"]


def _format_survivor_summary(result: Dict[str, object]) -> List[str]:
    lines = result["summary"][:5]
    alive = result["alive"]
    if alive:
        lines.append("Alive: " + ", ".join(str(team) for team in alive))
    return lines or ["No eliminations yet"]


def _maybe_post(cfg: Dict[str, object], key: str, title: str, lines: List[str], dry_run: bool) -> None:
    if dry_run:
        print(f"\n[{title}]")
        for line in lines:
            print(line)
        return

    discord.post_text(cfg, key, title, lines)


def main() -> None:
    """Entry point for the CLI application."""

    cfg = load_config()
    args = parse_args()

    espn_s2 = os.getenv("ESPN_S2", "")
    swid = os.getenv("SWID", "")
    league = get_league(
        league_id=int(cfg["league_id"]),
        season=int(cfg["season"]),
        espn_s2=espn_s2,
        swid=swid,
    )
    rules = extract_league_rules(league)
    regular_weeks = int(cfg.get("regular_season_weeks") or rules.get("regular_season_weeks") or 0)
    completed = last_completed_week(league)
    weeks = get_weeks(args.weeks, regular_weeks, last_completed=completed)

    payload: List[Dict[str, object]] = []
    for week in weeks:
        for team_score in fetch_week_scores(league, week):
            payload.append(asdict(team_score))

    base_df = build_base_frame(payload)
    scoring_df = add_optimal_points(base_df, rules)

    modes = [args.mode] if args.mode != "all" else ["pir", "efficiency", "survivor"]

    if "pir" in modes:
        pir_result = compute_pir(
            scoring_df,
            target=float(cfg.get("pir_target", 150.0)),
            tiebreaks=list((cfg.get("tiebreaks") or {}).get("pir", [])),
            weeks_scope=weeks,
        )
        _maybe_post(cfg, "pir", "Price Is Right", _format_pir_summary(pir_result), args.dry_run)

    if "efficiency" in modes:
        eff_result = season_efficiency(
            scoring_df,
            weeks=weeks,
            tiebreaks=list((cfg.get("tiebreaks") or {}).get("efficiency", [])),
        )
        _maybe_post(cfg, "efficiency", "Season Efficiency", _format_efficiency_summary(eff_result), args.dry_run)

    if "survivor" in modes:
        survivor_result = run_survivor(
            scoring_df,
            start_week=int(cfg.get("survivor_start_week", 1)),
            tiebreaks=list((cfg.get("tiebreaks") or {}).get("survivor", [])),
            weeks_scope=weeks,
        )
        _maybe_post(cfg, "survivor", "Survivor Pool", _format_survivor_summary(survivor_result), args.dry_run)


if __name__ == "__main__":
    main()
