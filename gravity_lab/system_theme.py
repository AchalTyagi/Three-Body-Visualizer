"""Detect the operating system's light/dark appearance using only the standard library.

``detect_system_theme()`` returns ``"Light"``, ``"Dark"`` or ``None`` when the setting
cannot be determined. It never raises, so callers can poll it freely.
"""
from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path
from typing import Callable, Mapping

_GNOME_SCHEMA = "org.gnome.desktop.interface"
_WINDOWS_KEY = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"


def theme_from_name(name: str) -> str | None:
    """Classify a GTK/KDE theme name such as ``Adwaita:dark`` or ``BreezeDark``."""
    lowered = name.strip().strip("'\"").lower()
    if not lowered:
        return None
    return "Dark" if "dark" in lowered else "Light"


def parse_gnome_color_scheme(text: str) -> str | None:
    """Parse ``gsettings get org.gnome.desktop.interface color-scheme`` output."""
    value = text.strip().strip("'\"").lower()
    if value == "prefer-dark":
        return "Dark"
    if value == "prefer-light":
        return "Light"
    return None  # 'default' (or unknown): the caller falls back to the GTK theme name


def parse_kdeglobals(text: str) -> str | None:
    """Read ``ColorScheme=`` from a ``kdeglobals`` file."""
    for line in text.splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip() == "ColorScheme":
            return theme_from_name(value)
    return None


def _run_text(run: Callable, command: list[str]) -> str:
    try:
        result = run(command, capture_output=True, text=True, timeout=2)
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout if result.returncode == 0 else ""


def _detect_windows(winreg_module) -> str | None:
    winreg = winreg_module
    if winreg is None:
        import winreg  # type: ignore[no-redef]
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _WINDOWS_KEY) as key:
        value, _kind = winreg.QueryValueEx(key, "AppsUseLightTheme")
    return "Light" if value else "Dark"


def _detect_macos(run: Callable) -> str | None:
    try:
        result = run(["defaults", "read", "-g", "AppleInterfaceStyle"],
                     capture_output=True, text=True, timeout=2)
    except (OSError, subprocess.SubprocessError):
        return None
    # The key only exists in dark mode; its absence (non-zero exit) means light.
    return "Dark" if result.returncode == 0 and "dark" in result.stdout.lower() else "Light"


def _detect_linux(run: Callable, environ: Mapping[str, str], home: Path) -> str | None:
    scheme = parse_gnome_color_scheme(_run_text(run, ["gsettings", "get", _GNOME_SCHEMA, "color-scheme"]))
    if scheme:
        return scheme
    gtk_name = environ.get("GTK_THEME") or _run_text(run, ["gsettings", "get", _GNOME_SCHEMA, "gtk-theme"])
    named = theme_from_name(gtk_name) if gtk_name else None
    if named:
        return named
    try:
        return parse_kdeglobals((home / ".config" / "kdeglobals").read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None


def detect_system_theme(*, system: str | None = None, run: Callable = subprocess.run,
                        environ: Mapping[str, str] | None = None, home: Path | None = None,
                        winreg_module=None) -> str | None:
    """Return the OS appearance as ``"Light"``/``"Dark"``, or ``None`` if unknown."""
    name = (system or platform.system()).lower()
    env = os.environ if environ is None else environ
    try:
        if name == "windows":
            return _detect_windows(winreg_module)
        if name == "darwin":
            return _detect_macos(run)
        return _detect_linux(run, env, Path.home() if home is None else home)
    except Exception:  # detection is best-effort and must never break the application
        return None
