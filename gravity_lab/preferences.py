"""Cross-platform user preferences for Gravity Lab 3D.

Preferences are intentionally separate from setup JSON and simulation checkpoints:
this file stores UI choices only, not body initial conditions or physics state.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from .themes import DEFAULT_THEME_MODE, FALLBACK_THEME, THEME_MODES, THEMES

PREFERENCES_SCHEMA = 1
APP_DIR_NAME = "GravityLab3D"
DEFAULT_PREFERENCES: dict[str, Any] = {
    "schema_version": PREFERENCES_SCHEMA,
    "theme": FALLBACK_THEME,  # palette last in use (informational)
    "theme_mode": DEFAULT_THEME_MODE,  # System, Light or Dark
    "view_mode": "3D",
    "speed": 1.0,
    "display_scale": 1.8,
    "trail": True,
    "floor": True,
    "axes": True,
    "shells": True,
    "field": True,
    "accel": False,
    "com": True,
    "autozoom": True,
    "view": "12",
    "trail_len": "1200",
}


def preferences_path(*, system: str | None = None, environ: Mapping[str, str] | None = None,
                     home: str | os.PathLike[str] | None = None) -> Path:
    """Return the conventional per-user configuration path for the target OS.

    Optional arguments make path selection deterministic in tests.
    """
    system = (system or os.name).lower()
    env = dict(os.environ if environ is None else environ)
    home_path = Path(home) if home is not None else Path.home()
    if system in ("nt", "windows"):
        root = Path(env.get("APPDATA") or (home_path / "AppData" / "Roaming"))
        return root / APP_DIR_NAME / "preferences.json"
    if system in ("darwin", "mac", "macos"):
        return home_path / "Library" / "Application Support" / APP_DIR_NAME / "preferences.json"
    root = Path(env.get("XDG_CONFIG_HOME") or (home_path / ".config"))
    return root / "gravity-lab-3d" / "preferences.json"


def validate_preferences(value: object) -> dict[str, Any]:
    """Validate and normalize preferences, ignoring unknown future keys."""
    if not isinstance(value, dict) or value.get("schema_version") != PREFERENCES_SCHEMA:
        raise ValueError("Unsupported Gravity Lab 3D preferences format.")
    data = dict(DEFAULT_PREFERENCES)
    data.update({key: item for key, item in value.items() if key in data})
    # Unknown or retired values (for example removed themes) fall back instead of discarding everything.
    if data["theme_mode"] not in THEME_MODES:
        data["theme_mode"] = DEFAULT_THEME_MODE
    if data["theme"] not in THEMES:
        data["theme"] = FALLBACK_THEME
    if data["view_mode"] not in ("2D", "3D"):
        raise ValueError("view_mode must be '2D' or '3D'.")
    for key in ("speed", "display_scale"):
        try:
            data[key] = float(data[key])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be numeric.") from exc
        if not 0.01 <= data[key] <= (100.0 if key == "speed" else 1000.0):
            raise ValueError(f"{key} is outside the supported range.")
    for key in ("trail", "floor", "axes", "shells", "field", "accel", "com", "autozoom"):
        if not isinstance(data[key], bool):
            raise ValueError(f"{key} must be true or false.")
    for key in ("view", "trail_len"):
        data[key] = str(data[key])
    return data


def load_preferences(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """Load preferences, falling back safely when absent or invalid."""
    target = Path(path) if path is not None else preferences_path()
    try:
        parsed = json.loads(target.read_text(encoding="utf-8"))
        return validate_preferences(parsed)
    except (OSError, json.JSONDecodeError, ValueError):
        return dict(DEFAULT_PREFERENCES)


def save_preferences(value: Mapping[str, Any], path: str | os.PathLike[str] | None = None) -> Path:
    """Atomically save validated preferences so partial writes are not left behind."""
    data = validate_preferences(dict(value))
    target = Path(path) if path is not None else preferences_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, target)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
    return target
