"""Small local appearance preference; no VPN data or credentials."""

import json
import os
from pathlib import Path

from .backend import save_private_file

MODES = ("system", "light", "dark")


def preference_path():
    root = os.environ.get("XDG_CONFIG_HOME", "")
    base = Path(root) if root and Path(root).is_absolute() else Path.home() / ".config"
    return base / "openvpn3-gui/preferences.json"


def read_mode(path=None):
    try:
        data = json.loads((path or preference_path()).read_text(encoding="utf-8"))
        value = data.get("appearance") if isinstance(data, dict) else None
        return value if value in MODES else "system"
    except (OSError, ValueError):
        return "system"


def write_mode(mode, path=None):
    if mode not in MODES:
        raise ValueError("Unknown appearance mode")
    path = path or preference_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    save_private_file(path, json.dumps({"appearance": mode}) + "\n")


def is_dark(mode, portal=None, desktop="default", fallback=False):
    if mode != "system":
        return mode == "dark"
    if portal in (1, 2):
        return portal == 1
    if desktop in ("prefer-dark", "prefer-light"):
        return desktop == "prefer-dark"
    return fallback
