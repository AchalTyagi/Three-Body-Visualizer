"""Backward-compatible import for the main Gravity Lab window.

The implementation lives in :mod:`gravity_lab.ui.main_window`; keeping these
exports preserves existing imports from ``gravity_lab.gui``.
"""
from .ui.main_window import BODY_FIELDS, CUSTOM_PRESET, GravityLabApp, _fmt, _rgba

__all__ = ["GravityLabApp", "BODY_FIELDS", "CUSTOM_PRESET"]
