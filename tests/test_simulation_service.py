"""Tests for the GUI-independent application-to-engine boundary."""

import subprocess
import sys

import pytest

from gravity_lab.physics import PASS, RK45
from gravity_lab.service import SimulationService, SimulationSnapshot, engine_from_state
from gravity_lab.state import BodyState, IntegratorSettings, PhysicsSettings, SimulationState


def sample_state():
    return SimulationState(
        bodies=(
            BodyState("Sun", 1.0, 0.01, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), color="#ffd166"),
            BodyState("Earth", 3.003e-6, 0.00004, (1.0, 0.0, 0.0), (0.0, 6.28, 0.0), color="#40c4ff"),
            BodyState("Moon", 3.7e-8, 0.00001, (1.0025, 0.0, 0.0), (0.0, 6.5, 0.0), color="#c4cbd4"),
        ),
        current_time=0.25,
        integrator=IntegratorSettings(method=RK45, dt=0.0001, steps_per_frame=10, adaptive=True,
                                      rtol=1e-10, atol=1e-13),
        physics=PhysicsSettings(gravitational_constant=39.47812, collision_mode=PASS,
                                units="Astronomical (AU, Msun, yr)"),
    )


def test_engine_factory_materializes_state_without_gui_dependencies():
    engine = engine_from_state(sample_state())
    assert engine.t == pytest.approx(0.25)
    assert engine.G == pytest.approx(39.47812)
    assert engine.collision == PASS
    assert engine.alive.tolist() == [True, True, True]
    assert engine.pos[1].tolist() == [1.0, 0.0, 0.0]


def test_service_reset_and_snapshot_expose_explicit_immutable_results():
    service = SimulationService()
    snapshot = service.reset(sample_state())
    assert isinstance(snapshot, SimulationSnapshot)
    assert snapshot.time == pytest.approx(0.25)
    assert snapshot.active == (True, True, True)
    assert snapshot.minimum_separation == pytest.approx(0.0025)
    assert service.state is not None
    assert service.state.bodies[1].name == "Earth"
    assert service.state.bodies[1].color == "#40c4ff"


def test_service_advance_updates_runtime_state_and_returns_snapshot():
    service = SimulationService(sample_state())
    before = service.snapshot()
    after = service.advance(steps=3, dt=1e-5, method=RK45, adaptive=True)
    assert after.time > before.time
    assert service.state is not None
    assert service.state.current_time == pytest.approx(after.time)
    assert service.state.integrator.method == RK45
    assert service.state.integrator.dt == pytest.approx(sample_state().integrator.dt)
    assert len(after.positions) == 3


def test_service_supports_inactive_body_sharing_position_with_active_body():
    state = SimulationState(
        bodies=(
            BodyState("Survivor", 2.0, 0.2, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
            BodyState("Merged", 1.0, 0.1, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), active=False),
            BodyState("Third", 0.5, 0.1, (3.0, 0.0, 0.0), (0.0, 0.2, 0.0)),
        ),
        physics=PhysicsSettings(collision_mode=PASS),
    )
    service = SimulationService(state)
    snap = service.snapshot()
    assert snap.active == (True, False, True)
    assert snap.positions[0] == snap.positions[1]
    assert service.state is not None
    assert service.state.bodies[1].mass > 0


def test_importing_service_does_not_import_gui_frameworks():
    # Use a fresh interpreter because other tests may already import Tk/VTK.
    code = (
        "import sys; import gravity_lab.service; "
        "assert 'tkinter' not in sys.modules; assert 'vtk' not in sys.modules"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_service_rejects_nonfinite_or_nonpositive_frame_overrides():
    service = SimulationService(sample_state())
    with pytest.raises(ValueError, match="time step must be finite and positive"):
        service.advance(dt=float("nan"))
    with pytest.raises(ValueError, match="step count must be finite and positive"):
        service.advance(steps=0)


def test_render_frame_is_read_only_and_contains_renderer_data():
    service = SimulationService(sample_state())
    frame = service.render_frame()
    assert frame.pos.shape == (3, 3)
    assert frame.accelerations().shape == (3, 3)
    assert frame.zone_radius(0) > 0
    assert frame.center_of_mass().shape == (3,)
    with pytest.raises(ValueError):
        frame.pos[0, 0] = 99


def test_service_can_restore_a_complete_saved_engine_state_and_time():
    import copy

    service = SimulationService(sample_state())
    saved_engine = copy.deepcopy(service.engine)
    assert saved_engine is not None
    saved_time = saved_engine.t
    service.advance(steps=2, dt=1e-5, method=RK45, adaptive=True)
    assert service.snapshot().time > saved_time

    restored = service.restore_engine(saved_engine)
    assert restored.time == pytest.approx(saved_time)
    assert service.engine is saved_engine
    assert service.state is not None
    assert service.state.current_time == pytest.approx(saved_time)
