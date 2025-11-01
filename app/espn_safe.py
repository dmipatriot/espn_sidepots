# app/espn_safe.py
from __future__ import annotations
import time
from typing import Any, Dict

_HTTP_BACKOFF = [0.6, 1.2, 2.4]  # seconds

def _is_json_response(r) -> bool:
    ct = (r.headers.get("Content-Type") or "").lower()
    if not ct.startswith("application/json"):
        return False
    # quick sanity on payload
    t = (r.text or "").lstrip()
    return t.startswith("{") or t.startswith("[")

def _try_json(r) -> Dict[str, Any] | None:
    try:
        return r.json()
    except Exception:
        return None

def league_get_safe(self, endpoint: str = "league", params: Dict[str, Any] | None = None, **kw) -> Dict[str, Any]:
    """
    Safe replacement for espn_api.requests.*Requests.league_get().
    Uses public self.get(...), retries on non-JSON or JSONDecodeError, logs snippet.
    """
    attempts = _HTTP_BACKOFF + [0]  # last try without sleep
    last_err = None

    for delay in attempts:
        # NOTE: the public method is .get(...), NOT _get(...)
        response = self.get(endpoint, params=params, **kw)  # <-- key fix
        if _is_json_response(response):
            data = _try_json(response)
            if data is not None:
                # their logger expects a dict; keep it small
                try:
                    self.logger.log_request(endpoint=endpoint, params=params or {}, headers={}, response=data)
                except Exception:
                    pass
                return data

        # non-JSON (usually HTML 200 bot page) or JSON parse fail
        snippet = (response.text or "")[:250]
        try:
            self.logger.log_request(
                endpoint=endpoint,
                params=params or {},
                headers={},
                response={"non_json": True, "status": response.status_code, "snippet": snippet},
            )
        except Exception:
            pass

        last_err = RuntimeError(
            f"ESPN returned non-JSON for '{endpoint}' (status={response.status_code}); snippet={snippet!r}"
        )
        if delay:
            time.sleep(delay)

    # exhausted retries
    raise last_err or RuntimeError("ESPN returned non-JSON for 'league' and no details available.")
