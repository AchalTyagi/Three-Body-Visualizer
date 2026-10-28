"""UI palettes for Gravity Lab 3D: one light and one dark theme, plus matching the system.

The gravity-field heatmap uses the same colour ramp in both themes, so identical field
values keep identical colours when the interface switches between light and dark.
"""
from __future__ import annotations

FIELD_HEATMAP_STOPS = ("#0b1026", "#3b0f70", "#8c2981", "#de4968", "#fe9f6d", "#fcfdbf")

THEMES = {
    # Soft charcoal surfaces with a muted blue accent.
    "Dark": {
        "app_bg": "#202124", "panel_bg": "#292a2d", "plot_bg": "#1b1c1e",
        "text": "#e8eaed", "muted": "#bdc1c6", "accent": "#a8c7fa",
        "entry_bg": "#303134", "border": "#444746", "button_bg": "#303134",
        "button_active": "#3c4043", "grid": "#62666b", "field_stops": list(FIELD_HEATMAP_STOPS),
    },
    # Off-white canvas, white panels and subtle borders.
    "Light": {
        "app_bg": "#f8f9fa", "panel_bg": "#ffffff", "plot_bg": "#fafbfc",
        "text": "#202124", "muted": "#5f6368", "accent": "#1a73e8",
        "entry_bg": "#ffffff", "border": "#dadce0", "button_bg": "#f1f3f4",
        "button_active": "#e8eaed", "grid": "#aeb4bb", "field_stops": list(FIELD_HEATMAP_STOPS),
    },
}

# "System" follows the operating system's light/dark setting.
THEME_MODES = ("System", "Light", "Dark")
DEFAULT_THEME_MODE = "System"
FALLBACK_THEME = "Dark"  # used when the system setting cannot be determined

BODY_COLORS = ("#40c4ff", "#ff6685", "#ffd166")
BODY_NAMES = ("CYAN", "CORAL", "GOLD")


def resolve_theme(mode: str, system_theme: str | None = None) -> str:
    """Return the palette name ("Light" or "Dark") for a theme mode.

    An explicit "Light"/"Dark" mode wins. Otherwise the detected system theme is used,
    falling back to ``FALLBACK_THEME`` when it is unknown.
    """
    if mode in THEMES:
        return mode
    if system_theme in THEMES:
        return system_theme
    return FALLBACK_THEME
