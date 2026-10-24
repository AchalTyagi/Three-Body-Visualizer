import numpy as np
import pytest

from gravity_lab.physics import PASS, ThreeBodyEngine


def make_engine(**kwargs):
    return ThreeBodyEngine(
        [1.2, 0.7, 2.1], [0.01, 0.02, 0.03],
        [[-1.0, 0.3, 0.5], [1.4, -0.7, 0.2], [0.2, 1.8, -0.9]],
        [[0.1, 0.2, 0.3], [-0.2, 0.1, 0.0], [0.0, -0.1, 0.2]],
        G=1.7, collision=PASS, **kwargs,
    )


def reference(engine, positions):
    p = np.asarray(positions, dtype=float)
    out = np.zeros((3, 3))
    for i in range(3):
        for j in range(3):
            if i == j or not (engine.alive[i] and engine.alive[j]):
                continue
            delta = p[j] - p[i]
            r2 = float(delta @ delta) + engine.eps2
            out[i] += engine.G * engine.m[j] * delta / (r2 ** 1.5)
    return out


@pytest.mark.parametrize("softening", [0.0, 0.03])
def test_fast_newtonian_pair_accumulation_matches_reference(softening):
    engine = make_engine(softening=softening)
    positions = np.array([[-1.2, 0.2, 0.1], [1.0, -0.3, 0.8], [0.1, 2.0, -0.5]])
    assert engine.accelerations(positions) == pytest.approx(reference(engine, positions), rel=1e-13, abs=1e-13)


def test_fast_path_skips_inactive_bodies():
    engine = make_engine()
    engine.alive[1] = False
    assert engine.accelerations() == pytest.approx(reference(engine, engine.pos), abs=1e-13)


def test_fast_path_raises_on_coincident_active_points():
    engine = make_engine()
    positions = engine.pos.copy()
    positions[1] = positions[0]
    with pytest.raises(FloatingPointError, match="coincident"):
        engine.accelerations(positions)
