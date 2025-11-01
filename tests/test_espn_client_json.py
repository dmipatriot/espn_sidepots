from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app import espn_client
import requests


class _FakeResponse:
    def __init__(
        self,
        status_code: int,
        body: str,
        json_payload: Dict[str, Any] | None = None,
        *,
        headers: Dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._body = body
        self._json_payload = json_payload
        self.headers = headers or {"Content-Type": "application/json"}

    @property
    def text(self) -> str:
        return self._body

    def json(self) -> dict:
        if self._json_payload is None:
            raise ValueError("Invalid JSON")
        return self._json_payload


def _set_context() -> None:
    espn_client._set_league_context(league_id=123456, season=2024)


def test_json_get_retries_and_recovers(monkeypatch, caplog):
    _set_context()
    monkeypatch.delenv("ESPN_USE_ALT_HOST", raising=False)

    calls: list[str] = []

    responses = [
        _FakeResponse(200, "not-json", headers={"Content-Type": "application/json"}),
        _FakeResponse(200, json.dumps({"ok": True}), {"ok": True}),
    ]

    def fake_get(self, url, params=None, cookies=None, timeout=None):
        calls.append(url)
        return responses[len(calls) - 1]

    monkeypatch.setattr(requests.Session, "get", fake_get)
    monkeypatch.setattr(espn_client.time, "sleep", lambda _s: None)

    with caplog.at_level(logging.DEBUG, espn_client.__name__):
        result = espn_client._json_get(
            "", params={"view": "mSettings"}, cookies={}, retries=1
        )

    assert result == {"ok": True}
    assert len(calls) == 2
    assert all("fantasy.espn.com" in url for url in calls)
    assert any("[http] ok host=fantasy" in message for message in caplog.messages)


def test_json_get_failover_to_alt_host(monkeypatch, caplog):
    _set_context()
    monkeypatch.delenv("ESPN_USE_ALT_HOST", raising=False)

    calls: list[str] = []

    def fake_get(self, url, params=None, cookies=None, timeout=None):
        calls.append(url)
        if "lm-api-reads" in url:
            return _FakeResponse(
                200,
                json.dumps({"ok": True}),
                {"ok": True},
            )
        return _FakeResponse(
            200,
            "<html>blocked</html>",
            headers={"Content-Type": "text/html; charset=utf-8"},
        )

    monkeypatch.setattr(requests.Session, "get", fake_get)
    monkeypatch.setattr(espn_client.time, "sleep", lambda _s: None)

    with caplog.at_level(logging.DEBUG, espn_client.__name__):
        result = espn_client._json_get(
            "", params={"view": "mSettings"}, cookies={}, retries=1
        )

    assert result == {"ok": True}
    assert any("fantasy.espn.com" in url for url in calls)
    assert any("lm-api-reads.fantasy.espn.com" in url for url in calls)
    assert any("[http] ok host=lm-api-reads" in message for message in caplog.messages)


def test_json_get_prefers_alt_host_when_forced(monkeypatch):
    _set_context()
    monkeypatch.setenv("ESPN_USE_ALT_HOST", "1")

    calls: list[str] = []

    def fake_get(self, url, params=None, cookies=None, timeout=None):
        calls.append(url)
        return _FakeResponse(200, json.dumps({"ok": True}), {"ok": True})

    monkeypatch.setattr(requests.Session, "get", fake_get)
    monkeypatch.setattr(espn_client.time, "sleep", lambda _s: None)

    result = espn_client._json_get(
        "", params={"view": "mSettings"}, cookies={}, retries=0
    )

    assert result == {"ok": True}
    assert calls[0].startswith("https://lm-api-reads.fantasy.espn.com")
