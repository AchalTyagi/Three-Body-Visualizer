"""Tests for the GUI-independent explicit simulation-state model."""
import json

import pytest

from gravity_lab.physics import PASS, RK45
from gravity_lab.state import BodyState, IntegratorSettings, PhysicsSettings, SimulationState


def sample_state():
    return SimulationState(
        bodies=(
            BodyState("Sun", 1.0, 0.01, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), color="#ffd166"),
            BodyState("Earth", 3.003e-6, 0.00004, (1.0, 0.0, 0.0), (0.0, 6.28, 0.0), color="#40c4ff"),
            BodyState("Moon", 3.7e-8, 0.00001, (1.0025, 0.0, 0.0), (0.0, 6.5, 0.0), color="#c4cbd4"),
        ),
        current_time=0.25,
        integrator=IntegratorSettings(method=RK45, dt=0.0001, steps_per_frame=10, adaptive=True, rtol=1e-10, atol=1e-13),
        physics=PhysicsSettings(gravitational_constant=39.47812, collision_mode=PASS, units="Astronomical (AU, Msun, yr)"),
    )


def test_state_mapping_round_trip_preserves_all_model_fields():
    original = sample_state()
    restored = SimulationState.from_mapping(json.loads(json.dumps(original.to_mapping())))
    assert restored == original
    assert restored.bodies[1].position == (1.0, 0.0, 0.0)
    assert restored.bodies[2].color == "#c4cbd4"
    assert restored.integrator.method == RK45
    assert restored.physics.units == "Astronomical (AU, Msun, yr)"
    assert restored.current_time == 0.25


def test_state_rejects_wrong_body_count():
    body = BodyState("one", 1, 0.1, (0, 0, 0), (0, 0, 0))
    with pytest.raises(ValueError, match="exactly three"):
        SimulationState(bodies=(body, body))  # type: ignore[arg-type]


@pytest.mark.parametrize("kwargs, message", [
    ({"mass": 0}, "mass must be greater"),
    ({"radius": float("inf")}, "radius must be finite"),
    ({"position": (0, 1)}, "exactly three numeric components"),
    ({"velocity": (0, float("nan"), 0)}, "must be finite"),
    ({"color": "red"}, "six-digit hex colour"),
    ({"name": "  "}, "name cannot be empty"),
])
def test_body_state_validates_fields(kwargs, message):
    data = dict(name="Body", mass=1, radius=0.1, position=(0, 0, 0), velocity=(0, 0, 0))
    data.update(kwargs)
    with pytest.raises(ValueError, match=message):
        BodyState(**data)


def test_integrator_settings_reject_invalid_step_and_tolerance():
    with pytest.raises(ValueError, match="Time step"):
        IntegratorSettings(dt=0)
    with pytest.raises(ValueError, match="relative tolerance"):
        IntegratorSettings(rtol=1.0)
    with pytest.raises(ValueError, match="integer"):
        IntegratorSettings(steps_per_frame=2.5)  # type: ignore[arg-type]


def test_physics_settings_rejects_invalid_collision_and_correction_softening():
    with pytest.raises(ValueError, match="Unknown collision mode"):
        PhysicsSettings(collision_mode="sometimes")
    with pytest.raises(ValueError, match="zero softening"):
        PhysicsSettings(enable_1pn=True, softening=1e-3)


def test_state_rejects_exact_coincidence_of_active_unsoftened_bodies():
    body1 = BodyState("A", 1, 0.1, (0, 0, 0), (0, 0, 0))
    body2 = BodyState("B", 1, 0.1, (0, 0, 0), (0, 1, 0))
    body3 = BodyState("C", 1, 0.1, (0, 2, 0), (0, 0, 1))
    with pytest.raises(ValueError, match="exact same position"):
        SimulationState((body1, body2, body3))


def test_inactive_body_may_share_position_with_active_body_for_collision_state():
    body1 = BodyState("A", 1, 0.1, (0, 0, 0), (0, 0, 0))
    body2 = BodyState("Merged remnant", 1, 0.1, (0, 0, 0), (0, 1, 0), active=False)
    body3 = BodyState("C", 1, 0.1, (0, 2, 0), (0, 0, 1))
    state = SimulationState((body1, body2, body3))
    assert not state.bodies[1].active


def test_1pn_and_tidal_damping_require_rk45():
    bodies = sample_state().bodies
    with pytest.raises(ValueError, match="require Dormand–Prince RK45"):
        SimulationState(bodies=bodies, integrator=IntegratorSettings(method="Yoshida (4th order, symplectic)"),
                        physics=PhysicsSettings(enable_1pn=True))
    with pytest.raises(ValueError, match="require Dormand–Prince RK45"):
        SimulationState(bodies=bodies, integrator=IntegratorSettings(method="Yoshida (4th order, symplectic)"),
                        physics=PhysicsSettings(tidal_damping=0.05))


def test_default_settings_are_explicit_and_state_is_immutable():
    from dataclasses import FrozenInstanceError, replace
    from gravity_lab.physics import YOSHIDA

    original = sample_state()
    assert original.integrator.method == RK45
    assert IntegratorSettings().method == YOSHIDA
    assert IntegratorSettings().steps_per_frame == 4
    changed = replace(original, current_time=original.current_time + 1.0)
    assert changed.current_time == 1.25
    assert original.current_time == 0.25
    with pytest.raises(FrozenInstanceError):
        original.current_time = 5.0  # type: ignore[misc]
