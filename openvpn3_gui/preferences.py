"""Small local desktop preferences; no VPN data or credentials."""

import json
import os
from pathlib import Path

from .backend import save_private_file

MODES = ("system", "light", "dark")


def preference_path():
    root = os.environ.get("XDG_CONFIG_HOME", "")
    base = Path(root) if root and Path(root).is_absolute() else Path.home() / ".config"
    return base / "openvpn3-gui/preferences.json"


def read_preferences(path=None):
    try:
        data = json.loads((path or preference_path()).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def read_mode(path=None):
    value = read_preferences(path).get("appearance")
    return value if value in MODES else "system"


def write_preference(key, value, path=None):
    path = path or preference_path()
    data = read_preferences(path)
    data[key] = value
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    save_private_file(path, json.dumps(data) + "\n")


def write_mode(mode, path=None):
    if mode not in MODES:
        raise ValueError("Unknown appearance mode")
    write_preference("appearance", mode, path)


def read_keep_running(path=None):
    value = read_preferences(path).get("keep_running", True)
    return value if type(value) is bool else True


def write_keep_running(enabled, path=None):
    if type(enabled) is not bool:
        raise ValueError("Expected a boolean")
    write_preference("keep_running", enabled, path)


def is_dark(mode, portal=None, desktop="default", fallback=False):
    if mode != "system":
        return mode == "dark"
    if portal in (1, 2):
        return portal == 1
    if desktop in ("prefer-dark", "prefer-light"):
        return desktop == "prefer-dark"
    return fallback
