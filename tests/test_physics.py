import math
import numpy as np

from gravity_lab.selftest import run_selftest
from gravity_lab.physics import ThreeBodyEngine, PASS, BOUNCE, RK45, VERLET
from gravity_lab.presets import PRESETS, engine_inputs


def test_physics_suite():
    assert run_selftest(verbose=False) == 0


def test_exact_inverse_square_force_when_unsoftened():
    engine = ThreeBodyEngine(
        [2.0, 3.0, 1e-16], [0.1, 0.1, 0.1],
        [[0, 0, 0], [2, 0, 0], [0, 1e6, 0]],
        [[0, 0, 0], [0, 0, 0], [0, 0, 0]], G=2.0, softening=0.0, collision=PASS
    )
    assert math.isclose(engine.accelerations()[0, 0], 1.5, rel_tol=0, abs_tol=1e-12)


def test_high_speed_bodies_do_not_tunnel_through_collision():
    engine = ThreeBodyEngine(
        [1, 1, 1], [0.5, 0.5, 0.1],
        [[-5, 0, 0], [5, 0, 0], [0, 100, 0]],
        [[100, 0, 0], [-100, 0, 0], [0, 0, 0]],
        G=0.0, softening=0.0, collision=BOUNCE, restitution=1.0
    )
    engine.step(0.2, VERLET)
    assert engine.vel[0, 0] < 0 < engine.vel[1, 0]
    assert len(engine.events) == 1
    assert math.isclose(engine.t, 0.2, abs_tol=1e-12)


def test_rk45_advances_exact_requested_interval():
    p = PRESETS["Figure-eight, tilted 40 deg (Claude)"]
    masses, radii, pos, vel = engine_inputs(p)
    engine = ThreeBodyEngine(masses, radii, pos, vel, p["G"], 0.0, collision=PASS, rtol=1e-8, atol=1e-11)
    initial = engine.pos.copy()
    period = 0.25
    while engine.t < period - 1e-12:
        engine.step(min(0.05, period - engine.t), RK45)
    assert math.isclose(engine.t, period, rel_tol=0, abs_tol=1e-11)
    assert engine.is_healthy()
    assert engine.rk45_accepted_steps > 0
    assert np.all(np.isfinite(engine.pos - initial))


def test_j2_force_matches_potential_gradient_and_is_optional():
    masses = [10.0, 1.0, 1e-10]
    radii = [0.5, 0.1, 0.1]
    positions = np.array([[0.0, 0.0, 0.0], [2.0, 0.2, 0.4], [10000.0, 0.0, 0.0]])
    velocities = np.zeros((3, 3))
    base = ThreeBodyEngine(masses, radii, positions, velocities, G=1.0, collision=PASS)
    oblate = ThreeBodyEngine(masses, radii, positions, velocities, G=1.0, collision=PASS,
                             enable_oblateness=True, j2=[0.1, 0.0, 0.0],
                             spin_axes=[[0, 0, 1], [0, 0, 1], [0, 0, 1]])
    assert not np.allclose(base.accelerations()[1], oblate.accelerations()[1])
    h = 1e-5
    x0 = oblate.pos[1, 0]
    oblate.pos[1, 0] = x0 + h; e_plus = oblate.energy()
    oblate.pos[1, 0] = x0 - h; e_minus = oblate.energy()
    oblate.pos[1, 0] = x0
    numerical_accel = -(e_plus - e_minus) / (2 * h * masses[1])
    assert math.isclose(oblate.accelerations()[1, 0], numerical_accel, rel_tol=1e-7, abs_tol=1e-8)


def test_pairwise_1pn_requires_rk45_and_preserves_pair_momentum():
    from gravity_lab.physics import YOSHIDA
    masses = [1.0, 2.0, 1e-10]
    radii = [0.01, 0.01, 0.01]
    positions = [[-1, 0, 0], [1, 0, 0], [0, 10000, 0]]
    velocities = [[0, -0.8, 0], [0, 0.4, 0], [0, 0, 0]]
    newton = ThreeBodyEngine(masses, radii, positions, velocities, G=1, collision=PASS)
    rel = ThreeBodyEngine(masses, radii, positions, velocities, G=1, collision=PASS,
                          enable_1pn=True, c_light=10.0)
    assert not np.allclose(newton.accelerations(), rel.accelerations(), rtol=0, atol=1e-12)
    net_force = np.sum(rel.m[:, None] * rel.accelerations(), axis=0)
    assert np.linalg.norm(net_force) < 1e-10
    try:
        rel.step(1e-4, YOSHIDA)
    except ValueError as exc:
        assert "require Dormand" in str(exc)
    else:
        raise AssertionError("1PN must require RK45 because its acceleration depends on velocity")
    rel.step(1e-4, RK45)
    assert rel.is_healthy()


def test_tidal_damping_records_heat_and_closes_energy_budget():
    engine = ThreeBodyEngine(
        [1, 1, 1], [0.1, 0.1, 0.1],
        [[-2, 0, 0], [2, 0, 0], [0, 50, 0]],
        [[1, 0, 0], [-1, 0, 0], [0, 0, 0]],
        G=0, collision=PASS, tidal_damping=0.5,
    )
    before = engine.linear_momentum().copy()
    engine.step(0.2, RK45)
    assert engine.tidal_energy_dissipated > 0
    assert engine.energy() < engine.e0
    assert engine.energy_error() < 1e-8
    np.testing.assert_allclose(engine.linear_momentum(), before, atol=1e-10)


def test_fragmentation_toy_model_conserves_pair_mass_and_momentum():
    from gravity_lab.physics import FRAGMENT, YOSHIDA
    engine = ThreeBodyEngine(
        [1, 1, 1], [0.6, 0.6, 0.1],
        [[-0.5, 0, 0], [0.5, 0, 0], [0, 10, 0]],
        [[1, 0, 0], [-1, 0, 0], [0, 0, 0]],
        G=0, collision=FRAGMENT,
    )
    mass_before = float(engine.m.sum())
    momentum_before = engine.linear_momentum().copy()
    angular_before = engine.angular_momentum().copy()
    engine.step(1e-5, YOSHIDA)
    assert len(engine.events) == 1 and "fragmented" in engine.events[-1][1]
    assert np.all(engine.alive)
    assert math.isclose(float(engine.m.sum()), mass_before, rel_tol=0, abs_tol=1e-12)
    np.testing.assert_allclose(engine.linear_momentum(), momentum_before, atol=1e-12)
    np.testing.assert_allclose(engine.angular_momentum(), angular_before, atol=1e-12)
    assert engine.energy_lost > 0


def test_j2_source_reaction_preserves_net_force():
    engine = ThreeBodyEngine(
        [10.0, 1.0, 1e-10], [0.5, 0.1, 0.1],
        [[0, 0, 0], [2, 0.2, 0.4], [10000, 0, 0]], np.zeros((3, 3)),
        G=1.0, collision=PASS, enable_oblateness=True, j2=[0.1, 0.0, 0.0]
    )
    np.testing.assert_allclose(np.sum(engine.m[:, None] * engine.accelerations(), axis=0), 0.0, atol=1e-10)

def test_spin_energy_and_angular_momentum_are_counted():
    engine = ThreeBodyEngine(
        [2.0, 1.0, 1e-10], [0.5, 0.1, 0.1],
        [[0, 0, 0], [2, 0, 0], [0, 1e6, 0]], np.zeros((3, 3)),
        G=0.0, collision=PASS, spin_omega=[[0, 0, 2], [0, 0, 0], [0, 0, 0]]
    )
    assert math.isclose(engine.angular_momentum()[2], 0.4, abs_tol=1e-12)
    assert math.isclose(engine.energy(), 0.4, abs_tol=1e-12)


def test_history_records_angular_momentum_drift_and_keeps_missing_pairs_nonfinite():
    from gravity_lab.physics import History, PASS

    engine = ThreeBodyEngine(
        [1.0, 1.0, 1.0], [0.01, 0.01, 0.01],
        [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
        [[0, 0, 0], [0, 1, 0], [-1, 0, 0]], G=1.0, collision=PASS,
    )
    history = History(maxlen=5)
    history.push(engine)
    assert len(history.angular_momentum_error) == 1
    assert np.isfinite(history.angular_momentum_error[-1])
    engine.alive[:] = [True, False, False]
    history.push(engine)
    assert all(np.isnan(series[-1]) for series in history.separations)
    assert len(history.angular_momentum_error) == 2
