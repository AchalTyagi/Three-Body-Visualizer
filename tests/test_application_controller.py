import pytest

from gravity_lab.application import SimulationController, state_from_preset
from gravity_lab.presets import PRESETS
from gravity_lab.service import SimulationService


def test_state_from_preset_preserves_physics_and_custom_display_metadata():
    name = next(iter(PRESETS))
    state = state_from_preset(name, body_names=("Sol", "Terra", "Luna"),
                              body_colors=("#ffcc00", "#2277ff", "#dddddd"))
    assert [body.name for body in state.bodies] == ["Sol", "Terra", "Luna"]
    assert [body.color for body in state.bodies] == ["#ffcc00", "#2277ff", "#dddddd"]
    assert state.physics.gravitational_constant == PRESETS[name]["G"]
    assert state.integrator.dt == PRESETS[name]["dt"]


def test_state_from_preset_rejects_unknown_and_malformed_presets():
    with pytest.raises(KeyError, match="Unknown preset"):
        state_from_preset("not a preset")
    with pytest.raises(ValueError, match="exactly three bodies"):
        state_from_preset("broken", {"broken": {"bodies": []}})


def test_controller_activates_preset_and_advances_without_gui_dependencies():
    controller = SimulationController(SimulationService())
    name = next(iter(PRESETS))
    before = controller.activate_preset(name)
    after = controller.advance(steps=1, dt=1e-7, adaptive=False)
    assert after.time > before.time
    assert controller.state is not None
    assert controller.state.current_time == pytest.approx(after.time)


def test_state_from_inputs_constructs_validated_domain_state():
    from gravity_lab.application import state_from_inputs
    state = state_from_preset(next(iter(PRESETS)))
    mapping = state.to_mapping()
    bodies = mapping["bodies"]
    values = {
        "m": [b["mass"] for b in bodies], "R": [b["radius"] for b in bodies],
        "pos": [b["position"] for b in bodies], "vel": [b["velocity"] for b in bodies],
        "j2": [b["j2"] for b in bodies], "spin_axes": [b["spin_axis"] for b in bodies],
        "spin_omega": [b["spin_omega"] for b in bodies],
        "dt": state.integrator.dt, "steps": state.integrator.steps_per_frame,
        "rtol": state.integrator.rtol, "atol": state.integrator.atol,
        "G": state.physics.gravitational_constant, "soft": state.physics.softening,
        "collision": state.physics.collision_mode, "restitution": state.physics.restitution,
        "enable_oblateness": state.physics.enable_oblateness, "enable_1pn": state.physics.enable_1pn,
        "c_light": state.physics.c_light, "tidal_damping": state.physics.tidal_damping,
    }
    built = state_from_inputs(values, body_names=[b["name"] for b in bodies],
                              body_colors=[b["color"] for b in bodies], units=state.physics.units,
                              integrator_method=state.integrator.method, adaptive=state.integrator.adaptive)
    assert built.to_mapping() == state.to_mapping()
