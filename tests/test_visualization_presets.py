from gravity_lab.ui.main_window import GravityLabApp


class Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeApp:
    _apply_visualization_preset = GravityLabApp._apply_visualization_preset

    def __init__(self, preset):
        self.visual_preset_var = Var(preset)
        self.trail_var = Var(True)
        self.floor_var = Var(True)
        self.shells_var = Var(True)
        self.axes_var = Var(True)
        self.field_var = Var(True)
        self.accel_var = Var(True)
        self.applied = 0

    def _apply_display_options(self):
        self.applied += 1


def test_orbit_study_preset_changes_display_only_toggles():
    app = FakeApp("Orbit study")
    app._apply_visualization_preset()
    assert [v.get() for v in (app.trail_var, app.floor_var, app.shells_var,
                              app.axes_var, app.field_var, app.accel_var)] == [True, False, False, True, False, False]
    assert app.visual_preset_var.get() == "Orbit study"
    assert app.applied == 1


def test_gravity_field_preset_enables_field_and_disables_clutter():
    app = FakeApp("Gravity field")
    app._apply_visualization_preset()
    assert app.field_var.get() is True
    assert app.trail_var.get() is False
    assert app.shells_var.get() is False
    assert app.applied == 1


def test_custom_visualization_selection_does_not_overwrite_user_choices():
    app = FakeApp("Custom")
    before = [v.get() for v in (app.trail_var, app.floor_var, app.shells_var,
                                app.axes_var, app.field_var, app.accel_var)]
    app._apply_visualization_preset()
    assert [v.get() for v in (app.trail_var, app.floor_var, app.shells_var,
                              app.axes_var, app.field_var, app.accel_var)] == before
    assert app.applied == 0
