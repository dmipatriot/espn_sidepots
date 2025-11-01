# app/espn_safe.py
from __future__ import annotations
import time
from typing import Any, Dict

_HTTP_BACKOFF = [0.6, 1.2, 2.4]  # seconds

def _is_json_response(r) -> bool:
    ct = (r.headers.get("Content-Type") or "").lower()
    if not ct.startswith("application/json"):
        return False
    t = (r.text or "").lstrip()
    return t.startswith("{") or t.startswith("[")

def _try_json(r):
    try:
        return r.json()
    except Exception:
        return None

def league_get_safe(self, endpoint: str = "league", params: Dict[str, Any] | None = None, **kw):
    """
    Safe replacement for espn_api ... .league_get().
    - Uses public self.get(...)
    - Retries on non-JSON / JSON parse errors
    - Normalizes kwargs so 'params' isn't passed twice
    """
    # --- normalize kwargs to avoid "multiple values for 'params'"
    if params is None and "params" in kw:
        params = kw.pop("params")
    else:
        # if both present, drop duplicate from kw
        kw.pop("params", None)
    headers = kw.pop("headers", None)  # optional, pass through once

    last_err = None
    for delay in _HTTP_BACKOFF + [0]:
        try:
            # pass each argument at most once
            call_kwargs = {}
            if params is not None:
                call_kwargs["params"] = params
            if headers is not None:
                call_kwargs["headers"] = headers
            call_kwargs.update(kw)

            resp = self.get(endpoint, **call_kwargs)
        except TypeError as e:
            # super defensive: if signature differs, try minimal call
            resp = self.get(endpoint, params=params)

        if _is_json_response(resp):
            data = _try_json(resp)
            if data is not None:
                try:
                    self.logger.log_request(endpoint=endpoint, params=params or {}, headers=headers or {}, response=data)
                except Exception:
                    pass
                return data

        snippet = (resp.text or "")[:250]
        try:
            self.logger.log_request(
                endpoint=endpoint,
                params=params or {},
                headers=headers or {},
                response={"non_json": True, "status": resp.status_code, "snippet": snippet},
            )
        except Exception:
            pass

        last_err = RuntimeError(f"ESPN returned non-JSON for '{endpoint}' (status={getattr(resp,'status_code', '?')}); snippet={snippet!r}")
        if delay:
            time.sleep(delay)

    raise last_err or RuntimeError("ESPN returned non-JSON for 'league' with no further details.")
