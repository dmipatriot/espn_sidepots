import os, requests

def _hook_from_cfg(cfg: dict, key: str) -> str | None:
    env_name = (cfg.get("webhooks") or {}).get(key)
    return os.getenv(env_name) if env_name else None

def post_text(cfg: dict, key: str, title: str, lines: list[str]):
    url = _hook_from_cfg(cfg, key)
    if not url:
        return
    body = { "embeds": [{ "title": title, "description": "\n".join(lines)[:4000] }] }
    r = requests.post(url, json=body, timeout=10)
    r.raise_for_status()
