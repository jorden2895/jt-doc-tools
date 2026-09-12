"""Settings storage for external GPU OCR server.

Stored in <data_dir>/ocr_remote.json, structure:
    {
        "enabled": false,
        "url": "http://10.0.0.5:8766",
        "token": "<bearer-token>",
        "timeout_s": 30,
        "last_test_ok": true,
        "last_test_at": "2026-05-26T16:00:00",
        "last_test_info": {...}  # /healthz response snapshot
    }

Token is stored on disk (chmod 600) — admin needs to be able to recall it
across jtdt restarts. SSH keys / passwords are NEVER stored (deploy flow only
processes them in-memory).
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from . import atomic_json
from ..config import settings

_LOCK = threading.RLock()
_FILE = Path(settings.data_dir) / "ocr_remote.json"

_DEFAULTS: dict[str, Any] = {
    "enabled": False,
    "url": "",
    "token": "",
    "timeout_s": 120,  # 首次請求需 Reader load + OCR + 網路;多語言 Reader 可能 30-60s
    "last_test_ok": False,
    "last_test_at": "",
    "last_test_info": {},
}


def _load() -> dict[str, Any]:
    if not _FILE.exists():
        return dict(_DEFAULTS)
    try:
        d = json.loads(_FILE.read_text(encoding="utf-8"))
    except Exception:
        return dict(_DEFAULTS)
    out = dict(_DEFAULTS)
    out.update(d)
    return out


def _save(d: dict[str, Any]) -> None:
    # 權限設在暫存檔上（helper 負責）—— 原本是 replace 之後才 chmod，
    # 那中間有一瞬間這個含 token 的檔案是 0644。
    atomic_json.write_json(_FILE, d, mode=0o600)


def get() -> dict[str, Any]:
    """Return a copy. Token is masked in caller as appropriate."""
    with _LOCK:
        return _load()


def update(*, url: str | None = None, token: str | None = None,
           enabled: bool | None = None, timeout_s: int | None = None) -> dict[str, Any]:
    with _LOCK:
        d = _load()
        if url is not None:
            d["url"] = url.strip().rstrip("/")
        if token is not None:
            d["token"] = token.strip()
        if enabled is not None:
            d["enabled"] = bool(enabled)
        if timeout_s is not None:
            d["timeout_s"] = max(5, min(600, int(timeout_s)))
        _save(d)
        return d


def update_test_result(*, ok: bool, info: dict[str, Any]) -> None:
    from datetime import datetime
    with _LOCK:
        d = _load()
        d["last_test_ok"] = bool(ok)
        d["last_test_at"] = datetime.now().isoformat(timespec="seconds")
        d["last_test_info"] = info
        _save(d)


def is_enabled_and_configured() -> bool:
    d = get()
    return bool(d.get("enabled")) and bool(d.get("url")) and bool(d.get("token"))


def masked_token(token: str) -> str:
    """For UI display — show first 6 + last 4 chars only."""
    if not token:
        return ""
    if len(token) <= 12:
        return "•" * len(token)
    return f"{token[:6]}…{token[-4:]}"
