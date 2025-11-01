from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app import espn_client


class _FakeResponse:
    def __init__(self, status_code: int, body: str, json_payload: dict | None = None):
        self.status_code = status_code
        self._body = body
        self._json_payload = json_payload
        self.headers = {"Content-Type": "application/json"}

    @property
    def text(self) -> str:
        return self._body

    def json(self) -> dict:
        if self._json_payload is None:
            raise ValueError("Invalid JSON")
        return self._json_payload


def test_json_get_retries_and_recovers(monkeypatch):
    calls: list[_FakeResponse] = []

    responses = [
        _FakeResponse(200, "not-json"),
        _FakeResponse(200, json.dumps({"ok": True}), {"ok": True}),
    ]

    def fake_get(url, params=None, cookies=None, headers=None, timeout=None):
        response = responses[len(calls)]
        calls.append(response)
        return response

    monkeypatch.setattr(espn_client.requests, "get", fake_get)
    monkeypatch.setattr(espn_client.time, "sleep", lambda _s: None)

    result = espn_client._json_get(
        "https://example.test", params={"view": "mSettings"}, cookies={}, retries=1
    )

    assert result == {"ok": True}
    assert len(calls) == 2
