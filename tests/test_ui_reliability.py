"""Headless regression tests for GUI reliability fixes (no Tk window is created)."""
import ast
import pathlib
import queue
from unittest.mock import MagicMock

from gravity_lab.presets import PRESETS
from gravity_lab.ui.main_window import GravityLabApp


class Var:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class TickApp:
    _tick = GravityLabApp._tick
    _post_ui = GravityLabApp._post_ui
    _drain_ui_queue = GravityLabApp._drain_ui_queue
    _handle_engine_error = GravityLabApp._handle_engine_error

    def __init__(self, tick_once):
        self._closed = False
        self._tick_after_id = "pending"
        self.engine = object()
        self.failed = False
        self.running = True
        self._dirty = True
        self.status_var = Var("")
        self.event_var = Var("")
        self._ui_queue = queue.Queue()
        self._tick_once = tick_once
        self.scheduled = 0

    def _schedule_tick(self):
        self.scheduled += 1


def test_tick_survives_engine_exception_and_keeps_loop_alive():
    def boom():
        raise RuntimeError("RK45 step underflow")

    app = TickApp(boom)
    app._tick()
    assert app.failed and not app.running and not app._dirty
    assert "RuntimeError" in app.status_var.get() and "RK45 step underflow" in app.event_var.get()
    assert app.scheduled == 1  # the loop is rescheduled even after a failure


def test_tick_reschedules_on_success_and_when_no_engine():
    app = TickApp(lambda: None)
    app._tick()
    app.engine = None
    app._tick()
    assert app.scheduled == 2 and not app.failed


def test_closed_app_does_not_reschedule():
    app = TickApp(lambda: None)
    app._closed = True
    app._tick()
    assert app.scheduled == 0


def test_ui_queue_runs_callbacks_in_order_and_survives_callback_errors():
    app = TickApp(lambda: None)
    seen = []
    app._post_ui(lambda: seen.append(1))
    app._post_ui(lambda: 1 / 0)
    app._post_ui(lambda: seen.append(2))
    app._tick()
    assert seen == [1, 2] and app.scheduled == 1 and not app.failed


class KeyApp:
    _on_key = GravityLabApp._on_key

    def __init__(self, focus_class=None):
        self.root = MagicMock(name="root")
        self.root.focus_get.return_value = None if focus_class is None else MagicMock(
            **{"winfo_class.return_value": focus_class})
        self.toggled = 0

    def _toggle_running(self):
        self.toggled += 1


def _key(app, widget_toplevel, keysym="space"):
    event = MagicMock()
    event.keysym = keysym
    event.widget.winfo_toplevel.return_value = widget_toplevel
    return event


def test_shortcuts_fire_from_main_window_only():
    app = KeyApp()
    app._on_key(_key(app, app.root))
    assert app.toggled == 1
    app._on_key(_key(app, object()))  # a dialog Toplevel
    assert app.toggled == 1


def test_shortcuts_ignored_while_typing():
    for cls in ("TEntry", "TCombobox", "Text", "TSpinbox"):
        app = KeyApp(focus_class=cls)
        app._on_key(_key(app, app.root))
        assert app.toggled == 0, cls


def test_loading_a_preset_resets_restitution():
    app = MagicMock(name="app")
    app.preset_var.get.return_value = next(iter(PRESETS))
    app.body_vars = [[MagicMock() for _ in range(8)] for _ in range(3)]
    app.j2_vars = [MagicMock() for _ in range(3)]
    app.spin_axis_vars = [[MagicMock() for _ in range(3)] for _ in range(3)]
    app.spin_omega_vars = [[MagicMock() for _ in range(3)] for _ in range(3)]
    GravityLabApp._load_preset(app)
    app.restitution_var.set.assert_called_with("1.0")


def test_no_broken_relative_imports_in_package():
    root = pathlib.Path(__file__).resolve().parents[1] / "gravity_lab"
    broken = []
    for path in root.rglob("*.py"):
        parts = path.relative_to(root.parent).with_suffix("").parts
        package = parts[:-1]
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.level:
                base = package[: len(package) - (node.level - 1)]
                target = root.parent.joinpath(*base, *(node.module.split(".") if node.module else []))
                if not (target.with_suffix(".py").exists() or (target / "__init__.py").exists()):
                    broken.append(f"{path.name}:{node.lineno} {'.' * node.level}{node.module or ''}")
    assert not broken, broken
