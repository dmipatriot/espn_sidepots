from __future__ import annotations

import time
from json import JSONDecodeError
from typing import Any, Dict

from requests import Response


http_backoff_delays = [0.6, 1.2, 2.4]


def is_json_response(response: Response) -> bool:
    """Return True when the response looks like JSON."""

    if response is None:
        return False
    content_type = (response.headers or {}).get("Content-Type", "")
    if not content_type.lower().startswith("application/json"):
        return False
    text = response.text or ""
    stripped = text.lstrip()
    if not stripped:
        return False
    return stripped[0] in "{["


def try_json(response: Response) -> Dict[str, Any] | None:
    """Attempt to parse JSON if the response looks valid."""

    if not is_json_response(response):
        return None
    try:
        data = response.json()
    except (ValueError, JSONDecodeError):
        return None
    if isinstance(data, dict):
        return data
    return None


def league_get_safe(self, endpoint: str = "league", params: Dict[str, Any] | None = None, **kw: Any) -> Dict[str, Any]:
    """
    Replacement for espn_api.requests.espn_requests.EspnRequests.league_get
    Retries on non-JSON or JSONDecodeError; logs short HTML snippet for diagnostics.
    Returns parsed JSON.
    """

    delays = http_backoff_delays + [0]
    for attempt, delay in enumerate(delays):
        response = self._get(endpoint, params=params, **kw)
        if is_json_response(response):
            try:
                data = response.json()
            except (ValueError, JSONDecodeError) as exc:
                snippet = (response.text or "")[:250]
                self.logger.log_request(
                    endpoint=endpoint,
                    params=params,
                    headers={},
                    response={
                        "json_error": True,
                        "status": response.status_code,
                        "snippet": snippet,
                        "error": str(exc),
                    },
                )
            else:
                self.logger.log_request(
                    endpoint=endpoint,
                    params=params,
                    headers={},
                    response=data,
                )
                return data
        else:
            snippet = (response.text or "")[:250]
            self.logger.log_request(
                endpoint=endpoint,
                params=params,
                headers={},
                response={
                    "non_json": True,
                    "status": response.status_code,
                    "snippet": snippet,
                },
            )

        if attempt < len(http_backoff_delays):
            time.sleep(delay)
            continue
        raise RuntimeError(
            "ESPN returned non-JSON for league endpoint after retries "
            f"(status={response.status_code})."
        )

    raise RuntimeError("league_get_safe retry loop exhausted unexpectedly")
