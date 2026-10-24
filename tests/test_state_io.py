import json

import pytest
import numpy as np

from gravity_lab.physics import PASS, RK45
from gravity_lab.service import SimulationService
from gravity_lab.state import BodyState, IntegratorSettings, PhysicsSettings, SimulationState
from gravity_lab.state_io import checkpoint_payload, load_checkpoint, save_checkpoint


def service_sample():
    state = SimulationState(
        bodies=(
            BodyState("Sun", 1, 0.01, (0, 0, 0), (0, 0, 0), color="#ffd166"),
            BodyState("Earth", 3e-6, 0.00004, (1, 0, 0), (0, 6.28, 0), color="#40c4ff"),
            BodyState("Moon", 3.7e-8, 0.00001, (1.0025, 0, 0), (0, 6.5, 0), color="#c4cbd4"),
        ),
        integrator=IntegratorSettings(method=RK45, dt=1e-5, steps_per_frame=2, adaptive=True),
        physics=PhysicsSettings(gravitational_constant=39.47812, collision_mode=PASS,
                               units="Astronomical (AU, Msun, yr)"),
    )
    service = SimulationService(state)
    service.advance(steps=2, dt=1e-6, method=RK45, adaptive=True)
    return service


def test_checkpoint_round_trip_restores_state_runtime_and_next_step(tmp_path):
    original = service_sample()
    path = save_checkpoint(original, tmp_path / "test.glcheckpoint.json")
    restored = load_checkpoint(path)
    assert restored.state is not None and original.state is not None
    assert restored.state.to_mapping() == original.state.to_mapping()
    assert restored.snapshot().positions == original.snapshot().positions
    assert restored.engine is not None and original.engine is not None
    assert list(restored.engine.events) == list(original.engine.events)
    assert restored.engine.rk45_accepted_steps == original.engine.rk45_accepted_steps
    a = original.step(h=1e-7, method=RK45)
    b = restored.step(h=1e-7, method=RK45)
    assert np.asarray(a.positions) == pytest.approx(np.asarray(b.positions))
    assert np.asarray(a.velocities) == pytest.approx(np.asarray(b.velocities))


def test_checkpoint_checksum_rejects_modified_payload(tmp_path):
    path = save_checkpoint(service_sample(), tmp_path / "test.json")
    payload = json.loads(path.read_text())
    payload["state"]["current_time"] += 10
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="checksum mismatch"):
        load_checkpoint(path)


def test_checkpoint_rejects_wrong_schema(tmp_path):
    payload = checkpoint_payload(service_sample())
    payload["schema_version"] = 999
    path = tmp_path / "future.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="Unsupported checkpoint schema"):
        load_checkpoint(path)
