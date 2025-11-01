from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.espn_client import build_member_display_map, build_team_label_map
from app.main import _format_survivor_summary
from app.survivor import run_survivor


SETTINGS_FIXTURE = {
    "members": [
        {
            "memberId": "GUID-AAA-0001",
            "displayName": "Kenny Thorson",
        },
        {
            "memberId": "GUID-BBB-0002",
            "firstName": "Taylor",
            "lastName": "Swift",
        },
        {
            "memberId": "GUID-CCC-0003",
            "alternateId": "alt-handle",
        },
        {
            "memberId": "deadbeef-0004",
        },
    ]
}


TEAMS_FIXTURE = {
    "teams": [
        {
            "id": 1,
            "location": "Iowa",
            "nickname": "Ironclads",
            "owners": ["GUID-AAA-0001"],
        },
        {
            "id": 2,
            "name": "Spoony Squad",
            "owners": ["GUID-BBB-0002"],
        },
    ]
}


BASIC_SETTINGS = {
    "members": [
        {"id": "ABC", "displayName": "Kenny Thorson"},
    ]
}


BASIC_TEAMS = {
    "teams": [
        {
            "id": 7,
            "location": "Iowa",
            "nickname": "Ironclads",
            "owners": ["ABC"],
        },
        {
            "id": 12,
            "name": "Spoony Squad",
            "owners": ["ABC"],
        },
    ]
}


def test_build_member_display_map_preference_chain():
    members = build_member_display_map(SETTINGS_FIXTURE)

    assert members["GUID-AAA-0001"] == "Kenny Thorson"
    assert members["GUID-BBB-0002"] == "Taylor Swift"
    assert members["GUID-CCC-0003"] == "alt-handle"
    assert members["deadbeef-0004"] == "DEADBE"


def test_build_team_label_map_uses_location_and_owner():
    member_map = build_member_display_map(SETTINGS_FIXTURE)
    labels = build_team_label_map(TEAMS_FIXTURE, member_map)

    assert labels[1] == "Iowa Ironclads (Kenny Thorson)"
    assert labels[2] == "Spoony Squad (Taylor Swift)"


def test_basic_fixture_matches_expected_labels():
    member_map = build_member_display_map(BASIC_SETTINGS)
    labels = build_team_label_map(BASIC_TEAMS, member_map)

    assert member_map["ABC"] == "Kenny Thorson"
    assert labels[7] == "Iowa Ironclads (Kenny Thorson)"
    assert labels[12] == "Spoony Squad (Kenny Thorson)"


def test_survivor_summary_uses_labels():
    df = pd.DataFrame(
        [
            {
                "team_id": 1,
                "owner": "kthorson59",
                "week": 1,
                "points": 120.0,
                "optimal_points": 150.0,
                "efficiency": 0.8,
            },
            {
                "team_id": 2,
                "owner": "GUID-BBB-0002",
                "week": 1,
                "points": 90.0,
                "optimal_points": 150.0,
                "efficiency": 0.6,
            },
        ]
    )
    member_map = build_member_display_map(SETTINGS_FIXTURE)
    labels = build_team_label_map(TEAMS_FIXTURE, member_map)

    result = run_survivor(df, start_week=1, weeks_scope=[1], labels=labels)

    assert all("GUID" not in line and "kthorson59" not in line for line in result["summary"])

    formatted = _format_survivor_summary(result, labels)
    assert any(labels[2] in line for line in formatted)
    assert any(labels[1] in line for line in formatted)
    assert all("GUID" not in line and "kthorson59" not in line for line in formatted)
