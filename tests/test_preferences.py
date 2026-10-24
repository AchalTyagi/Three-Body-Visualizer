import json
from pathlib import Path

import pytest

from gravity_lab.preferences import (
    DEFAULT_PREFERENCES,
    load_preferences,
    preferences_path,
    save_preferences,
    validate_preferences,
)


def test_preferences_path_is_platform_specific(tmp_path):
    win = preferences_path(system="nt", environ={"APPDATA": str(tmp_path / "roaming")}, home=tmp_path)
    mac = preferences_path(system="darwin", environ={}, home=tmp_path)
    linux = preferences_path(system="posix", environ={"XDG_CONFIG_HOME": str(tmp_path / "xdg")}, home=tmp_path)
    assert win == tmp_path / "roaming" / "GravityLab3D" / "preferences.json"
    assert mac == tmp_path / "Library" / "Application Support" / "GravityLab3D" / "preferences.json"
    assert linux == tmp_path / "xdg" / "gravity-lab-3d" / "preferences.json"


def test_preferences_round_trip_is_atomic_and_validated(tmp_path):
    path = tmp_path / "settings" / "preferences.json"
    expected = dict(DEFAULT_PREFERENCES, theme="Midnight Dark", view_mode="2D", speed=2.0, axes=False)
    save_preferences(expected, path)
    assert load_preferences(path) == expected
    assert json.loads(path.read_text(encoding="utf-8"))["theme"] == "Midnight Dark"
    assert not list(path.parent.glob("*.tmp"))


def test_missing_or_invalid_preferences_fall_back_to_defaults(tmp_path):
    path = tmp_path / "missing.json"
    assert load_preferences(path) == DEFAULT_PREFERENCES
    path.write_text('{broken', encoding="utf-8")
    assert load_preferences(path) == DEFAULT_PREFERENCES
    path.write_text('{"schema_version":99}', encoding="utf-8")
    assert load_preferences(path) == DEFAULT_PREFERENCES


def test_preferences_reject_invalid_numeric_and_boolean_values():
    with pytest.raises(ValueError):
        validate_preferences(dict(DEFAULT_PREFERENCES, speed=float("nan")))
    with pytest.raises(ValueError):
        validate_preferences(dict(DEFAULT_PREFERENCES, axes="false"))
