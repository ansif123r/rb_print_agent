from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

APP_DIR = Path(os.getenv("PROGRAMDATA", Path.home())) / "RB Print Agent"
CONFIG_FILE = APP_DIR / "config.json"

DEFAULTS: dict[str, Any] = {
    "erpnext_url": "https://rbfreshmart.m.frappe.cloud",
    "printer_name": "POS80 Printer",
    "erpnext_timeout": 15.0,
    "poll_interval": 3.0,
}


def _protect(value: str) -> str:
    if not value:
        return ""
    try:
        import win32crypt  # type: ignore
        encrypted = win32crypt.CryptProtectData(value.encode("utf-8"), "RB Print Agent", None, None, None, 0)[1]
        return "dpapi:" + base64.b64encode(encrypted).decode("ascii")
    except Exception:
        return value


def _unprotect(value: str) -> str:
    if not value:
        return ""
    if not value.startswith("dpapi:"):
        return value
    try:
        import win32crypt  # type: ignore
        encrypted = base64.b64decode(value[6:])
        return win32crypt.CryptUnprotectData(encrypted, None, None, None, 0)[1].decode("utf-8")
    except Exception:
        return ""


def load_config() -> dict[str, Any]:
    data: dict[str, Any] = dict(DEFAULTS)
    if CONFIG_FILE.exists():
        try:
            stored = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(stored, dict):
                data.update(stored)
        except Exception:
            pass

    data["erpnext_url"] = os.getenv("RB_AGENT_ERPNEXT_URL", str(data.get("erpnext_url", "")).strip()).strip()
    data["erpnext_token"] = os.getenv("RB_AGENT_TOKEN", _unprotect(str(data.get("erpnext_token", "")))).strip()
    data["printer_name"] = os.getenv("RB_AGENT_PRINTER", str(data.get("printer_name", "POS80 Printer"))).strip()
    data["erpnext_timeout"] = float(os.getenv("RB_AGENT_ERPNEXT_TIMEOUT", data.get("erpnext_timeout", 15)))
    data["poll_interval"] = float(os.getenv("RB_AGENT_POLL_INTERVAL", data.get("poll_interval", 3)))
    return data


def save_config(erpnext_url: str, token: str, printer_name: str, timeout: float = 15.0, poll_interval: float = 3.0) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "erpnext_url": erpnext_url.strip().rstrip("/"),
        "erpnext_token": _protect(token.strip()),
        "printer_name": printer_name.strip(),
        "erpnext_timeout": float(timeout),
        "poll_interval": float(poll_interval),
    }
    CONFIG_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def is_configured() -> bool:
    data = load_config()
    return bool(data.get("erpnext_url") and data.get("erpnext_token") and data.get("printer_name"))
