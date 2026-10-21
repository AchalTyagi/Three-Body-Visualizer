import numpy as np

from gravity_lab.presets import PRESETS, engine_inputs
from gravity_lab.physics import RK45, ThreeBodyEngine
from gravity_lab.themes import THEMES

EXPECTED_GALLERY = {
    "Butterfly I", "Butterfly II", "Butterfly III", "Butterfly IV", "Bumblebee",
    "Dragonfly", "Figure-eight", "Goggles", "Moth I", "Moth II", "Moth III", "Yarn",
    "Yin-Yang I (A)", "Yin-Yang I (B)", "Yin-Yang II (A)", "Yin-Yang II (B)",
}


def test_preset_dropdown_contains_only_image_gallery_models():
    assert set(PRESETS) == EXPECTED_GALLERY
    assert all("Periodic ·" not in name and "T≈" not in name for name in PRESETS)
    assert all(preset["model_name"] == name for name, preset in PRESETS.items())


def test_periodic_presets_have_valid_equal_mass_point_mass_setup():
    for name, preset in PRESETS.items():
        masses, radii, pos, vel = engine_inputs(preset)
        assert preset["G"] == 1.0, name
        assert preset["soft"] == 0.0, name
        assert preset["collision"] == "Pass through", name
        assert preset["integrator"] == RK45, name
        assert preset["period"] > 0, name
        assert preset["show_shells"] is False, name
        assert preset["show_field"] is False, name
        assert preset["show_trails"] is True, name
        assert preset["display_scale"] >= 10.0, name
        np.testing.assert_allclose(masses, [1, 1, 1])
        assert np.all(np.asarray(radii) > 0)
        np.testing.assert_allclose(np.sum(np.asarray(masses)[:, None] * np.asarray(pos), axis=0), 0, atol=1e-12)
        np.testing.assert_allclose(np.sum(np.asarray(masses)[:, None] * np.asarray(vel), axis=0), 0, atol=1e-12)


def test_minimal_dark_and_expanded_themes_have_all_required_palette_fields():
    assert "Minimal Dark" in THEMES
    assert len(THEMES) >= 11
    required = {"app_bg", "panel_bg", "plot_bg", "text", "muted", "accent", "entry_bg",
                "border", "button_bg", "button_active", "grid", "field_stops"}
    for name, palette in THEMES.items():
        assert required <= palette.keys(), name
        assert len(palette["field_stops"]) >= 4, name


def test_classic_figure_eight_closes_numerically():
    preset = PRESETS["Figure-eight"]
    masses, radii, pos, vel = engine_inputs(preset)
    engine = ThreeBodyEngine(masses, radii, pos, vel, preset["G"], preset["soft"],
                             collision=preset["collision"], rtol=1e-10, atol=1e-13)
    initial = engine.pos.copy()
    nsteps = 300
    dt = preset["period"] / nsteps
    for _ in range(nsteps):
        engine.step(dt, RK45)
    assert np.max(np.abs(engine.pos - initial)) < 1e-7
    assert engine.energy_error() < 1e-8
