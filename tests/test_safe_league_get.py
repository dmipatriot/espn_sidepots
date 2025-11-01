from __future__ import annotations

import json

import pytest

from app.espn_safe import is_json_response, league_get_safe, try_json


class FakeResponse:
    def __init__(self, text: str, content_type: str = "application/json", status: int = 200):
        self.text = text
        self.status_code = status
        self.headers = {"Content-Type": content_type}

    def json(self):
        return json.loads(self.text)


class FakeLogger:
    def __init__(self):
        self.logged = []

    def log_request(self, **details):
        self.logged.append(details)


class FakeRequests:
    def __init__(self, responses):
        self._responses = iter(responses)
        self.logger = FakeLogger()

    def _get(self, endpoint, params=None, **kw):  # pragma: no cover - signature compatibility
        try:
            return next(self._responses)
        except StopIteration:  # pragma: no cover - defensive
            raise AssertionError("No more fake responses queued")


def test_is_json_response_true():
    resp = FakeResponse("{\"ok\": true}")
    assert is_json_response(resp)


def test_is_json_response_false_for_html():
    resp = FakeResponse("<html></html>", content_type="text/html")
    assert not is_json_response(resp)


def test_try_json_success():
    resp = FakeResponse("{\"value\": 1}")
    assert try_json(resp) == {"value": 1}


def test_try_json_none_for_non_json():
    resp = FakeResponse("<html></html>", content_type="text/html")
    assert try_json(resp) is None


def test_league_get_safe_returns_json(monkeypatch):
    json_response = FakeResponse("{\"data\": 42}")
    fake = FakeRequests([json_response])
    monkeypatch.setattr("app.espn_safe.time.sleep", lambda *_: None)
    result = league_get_safe(fake, "league", params={"view": "mSettings"})
    assert result == {"data": 42}
    assert len(fake.logger.logged) == 1
    assert fake.logger.logged[0]["response"] == {"data": 42}


def test_league_get_safe_raises_after_retries(monkeypatch):
    monkeypatch.setattr("app.espn_safe.time.sleep", lambda *_: None)
    monkeypatch.setattr("app.espn_safe.http_backoff_delays", [0, 0, 0])
    html_response = FakeResponse("<html><body>Error</body></html>", content_type="text/html")
    fake = FakeRequests([html_response, html_response, html_response, html_response])
    with pytest.raises(RuntimeError):
        league_get_safe(fake, "league")
    assert len(fake.logger.logged) == 4
    for entry in fake.logger.logged:
        assert entry["response"]["non_json"] is True
        assert "snippet" in entry["response"]
