"""Theme-mode behaviour of the main window, tested without creating a Tk window."""

import gravity_lab.ui.main_window as main_window
from gravity_lab.ui.main_window import GravityLabApp


class Var:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeRoot:
    def __init__(self):
        self.after_calls = []

    def after(self, delay, callback):
        self.after_calls.append((delay, callback))


class ThemeApp:
    SYSTEM_THEME_POLL_SECONDS = GravityLabApp.SYSTEM_THEME_POLL_SECONDS
    _resolve_theme = GravityLabApp._resolve_theme
    _on_theme_mode_changed = GravityLabApp._on_theme_mode_changed
    _schedule_theme_check = GravityLabApp._schedule_theme_check
    _check_system_theme = GravityLabApp._check_system_theme

    def __init__(self, mode="System", theme="Dark", system_theme=None):
        self.theme_mode_var, self.theme_var, self.event_var = Var(mode), Var(theme), Var("")
        self._system_theme, self._closed = system_theme, False
        self.root = FakeRoot()
        self.applied = 0

    def _apply_theme(self):
        self.applied += 1


def test_system_mode_asks_the_os_and_explicit_modes_do_not(monkeypatch):
    monkeypatch.setattr(main_window, "detect_system_theme", lambda: "Light")
    assert ThemeApp("System")._resolve_theme() == "Light"

    def forbidden():
        raise AssertionError("explicit modes must not query the OS")

    monkeypatch.setattr(main_window, "detect_system_theme", forbidden)
    assert ThemeApp("Dark")._resolve_theme() == "Dark"
    assert ThemeApp("Light")._resolve_theme() == "Light"


def test_unknown_os_setting_falls_back_to_dark(monkeypatch):
    monkeypatch.setattr(main_window, "detect_system_theme", lambda: None)
    assert ThemeApp("System", theme="Light")._resolve_theme() == "Dark"


def test_changing_mode_updates_the_palette_and_applies_it(monkeypatch):
    monkeypatch.setattr(main_window, "detect_system_theme", lambda: "Light")
    app = ThemeApp("System", theme="Dark")
    app._on_theme_mode_changed()
    assert app.theme_var.get() == "Light" and app.applied == 1
    app.theme_mode_var.set("Dark")
    app._on_theme_mode_changed()
    assert app.theme_var.get() == "Dark" and app.applied == 2


def test_watcher_applies_a_changed_system_theme_and_keeps_polling():
    app = ThemeApp("System", theme="Dark", system_theme="Light")
    app._check_system_theme()
    assert app.theme_var.get() == "Light" and app.applied == 1
    assert len(app.root.after_calls) == 1
    app._check_system_theme()  # unchanged -> nothing to apply
    assert app.applied == 1 and len(app.root.after_calls) == 2


def test_watcher_ignores_the_os_when_a_mode_is_pinned_or_detection_failed():
    for mode, detected in (("Dark", "Light"), ("Light", "Dark"), ("System", None)):
        app = ThemeApp(mode, theme="Dark" if mode != "Light" else "Light", system_theme=detected)
        before = app.theme_var.get()
        app._check_system_theme()
        assert app.theme_var.get() == before and app.applied == 0


def test_watcher_survives_errors_and_stops_when_closed():
    app = ThemeApp("System", theme="Dark", system_theme="Light")

    def broken():
        raise RuntimeError("style failure")

    app._apply_theme = broken
    app._check_system_theme()  # must not raise
    assert len(app.root.after_calls) == 1
    app._closed = True
    app._check_system_theme()
    assert len(app.root.after_calls) == 1  # no further scheduling after close
