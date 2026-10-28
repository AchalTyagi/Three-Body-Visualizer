import numpy as np

from gravity_lab.presets import PRESETS, engine_inputs
from gravity_lab.physics import RK45, ThreeBodyEngine
from gravity_lab.themes import THEMES

EXPECTED_GALLERY = {
    "Butterfly I", "Butterfly II", "Butterfly III", "Butterfly IV", "Bumblebee",
    "Moth I", "Moth II", "Moth III", "Goggles", "Yin-Yang I", "Dragonfly", "Yarn",
    "Yin-Yang I · branch b", "Yin-Yang II · branch a", "Yin-Yang II · branch b",
    "Figure-eight (classic)", "Euler collinear rotating", "Lagrange equilateral",
}


def test_periodic_gallery_is_complete_and_uses_pass_through_point_mass_setup():
    gallery = {name: preset for name, preset in PRESETS.items() if name.startswith("Periodic · ")}
    labels = {preset["model_name"] for preset in gallery.values()}
    assert EXPECTED_GALLERY == labels
    for preset in gallery.values():
        masses, radii, pos, vel = engine_inputs(preset)
        assert preset["G"] == 1.0
        assert preset["soft"] == 0.0
        assert preset["collision"] == "Pass through"
        assert preset["integrator"] == RK45
        assert preset["period"] > 0
        assert preset["show_shells"] is False
        assert preset["show_field"] is False
        assert preset["show_trails"] is True
        assert preset["display_scale"] >= 10.0  # visual exaggeration only; physical radius stays small
        np.testing.assert_allclose(masses, [1, 1, 1])
        assert np.all(np.asarray(radii) > 0)
        np.testing.assert_allclose(np.sum(np.asarray(masses)[:, None] * np.asarray(pos), axis=0), 0, atol=1e-12)
        np.testing.assert_allclose(np.sum(np.asarray(masses)[:, None] * np.asarray(vel), axis=0), 0, atol=1e-12)


def test_light_and_dark_themes_have_all_required_palette_fields():
    assert tuple(THEMES) == ("Dark", "Light")
    required = {"app_bg", "panel_bg", "plot_bg", "text", "muted", "accent", "entry_bg",
                "border", "button_bg", "button_active", "grid", "field_stops"}
    for name, palette in THEMES.items():
        assert required <= palette.keys(), name
        assert len(palette["field_stops"]) >= 4, name


def test_classical_euler_and_lagrange_orbits_close_numerically():
    for label in ("Euler collinear rotating", "Lagrange equilateral"):
        preset = next(p for p in PRESETS.values() if p.get("model_name") == label)
        masses, radii, pos, vel = engine_inputs(preset)
        engine = ThreeBodyEngine(masses, radii, pos, vel, preset["G"], preset["soft"],
                                 collision=preset["collision"], rtol=1e-10, atol=1e-13)
        initial = engine.pos.copy()
        steps = 300
        dt = preset["period"] / steps
        for _ in range(steps):
            engine.step(dt, RK45)
        assert np.max(np.abs(engine.pos - initial)) < 1e-7
        assert engine.energy_error() < 1e-8
