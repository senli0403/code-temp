"""Local settings: API keys live in the user's home dir, never in the code."""
import json
import os
from pathlib import Path

HOME = Path(os.environ.get("NQ_KLINE_HOME") or Path.home() / ".nq_kline")
CONFIG_FILE = HOME / "config.json"
CACHE_DIR = HOME / "cache"
NOTES_FILE = HOME / "notes.json"
HISTORY_FILE = HOME / "chat_history.json"

DEFAULTS = {
    "databento_key": "",
    "anthropic_key": "",
    "model": "claude-sonnet-5-5",
    "symbol": "NQ.v.0",
    "dataset": "GLBX.MDP3",
    "timezone": "Asia/Taipei",
}


def ensure_dirs() -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def load() -> dict:
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    # environment variables win when the file has no key
    cfg["databento_key"] = cfg["databento_key"] or os.environ.get("DATABENTO_API_KEY", "")
    cfg["anthropic_key"] = cfg["anthropic_key"] or os.environ.get("ANTHROPIC_API_KEY", "")
    return cfg


def save(updates: dict) -> dict:
    ensure_dirs()
    cfg = load()
    for k, v in updates.items():
        if k in DEFAULTS and v is not None:
            cfg[k] = v.strip() if isinstance(v, str) else v
    CONFIG_FILE.write_text(json.dumps({k: cfg[k] for k in DEFAULTS}, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(CONFIG_FILE, 0o600)
    except OSError:
        pass
    return cfg


def mask(key: str) -> str:
    if not key:
        return ""
    return key[:4] + "…" + key[-3:] if len(key) > 8 else "已設定"


def public(cfg: dict) -> dict:
    out = {k: v for k, v in cfg.items() if not k.endswith("_key")}
    out["databento_key_set"] = bool(cfg["databento_key"])
    out["anthropic_key_set"] = bool(cfg["anthropic_key"])
    out["databento_key_hint"] = mask(cfg["databento_key"])
    out["anthropic_key_hint"] = mask(cfg["anthropic_key"])
    return out
