"""Light/Dark themes, system-theme detection and preference handling (no GUI needed)."""
import json
from pathlib import Path
from types import SimpleNamespace

from gravity_lab.preferences import DEFAULT_PREFERENCES, load_preferences, validate_preferences
from gravity_lab.system_theme import (
    detect_system_theme,
    parse_gnome_color_scheme,
    parse_kdeglobals,
    theme_from_name,
)
from gravity_lab.themes import DEFAULT_THEME_MODE, THEME_MODES, THEMES, resolve_theme


def runner(stdout="", returncode=0, error=None):
    def run(command, **_kwargs):
        if error:
            raise error
        return SimpleNamespace(returncode=returncode, stdout=stdout)
    return run


def by_command(table):
    """Fake subprocess.run keyed on the last argument (e.g. 'color-scheme')."""
    def run(command, **_kwargs):
        stdout = table.get(command[-1])
        return SimpleNamespace(returncode=0 if stdout is not None else 1, stdout=stdout or "")
    return run


class FakeWinreg:
    HKEY_CURRENT_USER = object()

    def __init__(self, value=None, error=None):
        self.value, self.error = value, error

    def OpenKey(self, *_args):
        if self.error:
            raise self.error
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def QueryValueEx(self, _key, name):
        assert name == "AppsUseLightTheme"
        return self.value, 4


def test_only_light_and_dark_themes_exist_with_a_system_mode():
    assert set(THEMES) == {"Light", "Dark"}
    assert THEME_MODES == ("System", "Light", "Dark") and DEFAULT_THEME_MODE == "System"


def test_resolve_theme_prefers_explicit_mode_then_system_then_dark():
    assert resolve_theme("Light", "Dark") == "Light"
    assert resolve_theme("Dark", "Light") == "Dark"
    assert resolve_theme("System", "Light") == "Light"
    assert resolve_theme("System", "Dark") == "Dark"
    assert resolve_theme("System", None) == "Dark"
    assert resolve_theme("Midnight Dark", None) == "Dark"  # retired names never crash


def test_windows_registry_value_maps_to_theme():
    assert detect_system_theme(system="Windows", winreg_module=FakeWinreg(1)) == "Light"
    assert detect_system_theme(system="Windows", winreg_module=FakeWinreg(0)) == "Dark"
    assert detect_system_theme(system="Windows", winreg_module=FakeWinreg(error=OSError("no key"))) is None


def test_macos_defaults_key_present_means_dark_absent_means_light():
    assert detect_system_theme(system="Darwin", run=runner("Dark\n")) == "Dark"
    assert detect_system_theme(system="Darwin", run=runner("", returncode=1)) == "Light"
    assert detect_system_theme(system="Darwin", run=runner(error=FileNotFoundError())) is None


def test_gnome_color_scheme_then_gtk_theme_then_kde_fallbacks(tmp_path):
    home = tmp_path
    assert detect_system_theme(system="Linux", environ={}, home=home,
                               run=by_command({"color-scheme": "'prefer-dark'\n"})) == "Dark"
    assert detect_system_theme(system="Linux", environ={}, home=home,
                               run=by_command({"color-scheme": "'prefer-light'\n"})) == "Light"
    # 'default' defers to the GTK theme name.
    assert detect_system_theme(system="Linux", environ={}, home=home,
                               run=by_command({"color-scheme": "'default'\n", "gtk-theme": "'Adwaita-dark'\n"})) == "Dark"
    assert detect_system_theme(system="Linux", environ={"GTK_THEME": "Adwaita:dark"}, home=home,
                               run=runner(error=FileNotFoundError())) == "Dark"
    (home / ".config").mkdir()
    (home / ".config" / "kdeglobals").write_text("[General]\nColorScheme=BreezeDark\n", encoding="utf-8")
    assert detect_system_theme(system="Linux", environ={}, home=home,
                               run=runner(error=FileNotFoundError())) == "Dark"


def test_unknown_linux_setup_returns_none_and_never_raises(tmp_path):
    assert detect_system_theme(system="Linux", environ={}, home=tmp_path,
                               run=runner(error=FileNotFoundError())) is None
    assert detect_system_theme(system="Linux", environ={}, home=tmp_path,
                               run=runner(error=RuntimeError("boom"))) is None


def test_name_and_file_parsers():
    assert theme_from_name("Adwaita:dark") == "Dark" and theme_from_name("Yaru") == "Light"
    assert theme_from_name("  ") is None
    assert parse_gnome_color_scheme("'default'") is None
    assert parse_kdeglobals("[General]\nColorScheme=BreezeLight\n") == "Light"
    assert parse_kdeglobals("[General]\nName=x\n") is None


def test_preferences_default_to_system_mode_and_normalize_retired_values(tmp_path):
    assert DEFAULT_PREFERENCES["theme_mode"] == "System"
    # An old preferences file (no theme_mode, a removed theme name) loads cleanly in System mode.
    legacy = dict(DEFAULT_PREFERENCES)
    legacy.pop("theme_mode")
    legacy["theme"] = "Midnight Dark"
    loaded = validate_preferences(legacy)
    assert loaded["theme_mode"] == "System" and loaded["theme"] == "Dark"
    assert validate_preferences(dict(DEFAULT_PREFERENCES, theme_mode="Neon"))["theme_mode"] == "System"
    path: Path = tmp_path / "preferences.json"
    path.write_text(json.dumps(dict(DEFAULT_PREFERENCES, theme_mode="Light", theme="Light")), encoding="utf-8")
    assert load_preferences(path)["theme_mode"] == "Light"
