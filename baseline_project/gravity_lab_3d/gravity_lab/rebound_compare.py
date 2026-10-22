"""Optional comparison of the built-in integrator against REBOUND IAS15.

REBOUND is optional and does not power the live GUI. The comparison evolves the
same unsoftened, collision-free three-body initial state in both engines and
reports trajectory differences at identical sample times.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
import numpy as np

from .physics import ThreeBodyEngine, RK45, PASS


@dataclass(frozen=True)
class ReboundComparison:
    duration: float
    samples: int
    rms_position_error: float
    max_position_error: float
    characteristic_separation: float
    relative_rms_error: float
    relative_max_error: float
    reference_integrator: str = "REBOUND IAS15"
    local_integrator: str = "Dormand–Prince RK45"


def compare_against_rebound(masses, radii, positions, velocities, G, duration,
                            samples=128, softening=0.0, rtol=1e-9, atol=1e-12) -> ReboundComparison:
    """Compare local RK45 against REBOUND IAS15 for an unsoftened three-body system.

    Collision handling is deliberately disabled in both compared trajectories.
    Use non-overlapping initial conditions and choose a duration that avoids physical
    contacts; otherwise this measures point-mass dynamics rather than collision physics.
    """
    try:
        import rebound
    except ImportError as exc:
        raise RuntimeError("REBOUND is not installed. Install it with: python -m pip install rebound") from exc
    if softening != 0:
        raise ValueError("REBOUND comparison currently requires softening ε = 0.")
    if not math.isfinite(float(duration)) or duration <= 0:
        raise ValueError("Comparison duration must be finite and positive.")
    samples = int(samples)
    if samples < 2 or samples > 5000:
        raise ValueError("Sample count must be between 2 and 5000.")
    m = np.asarray(masses, dtype=float).reshape(3)
    r = np.asarray(radii, dtype=float).reshape(3)
    p0 = np.asarray(positions, dtype=float).reshape(3, 3)
    v0 = np.asarray(velocities, dtype=float).reshape(3, 3)
    if np.any(m <= 0) or not np.all(np.isfinite(p0)) or not np.all(np.isfinite(v0)):
        raise ValueError("Initial masses must be positive and state vectors finite.")

    sim = rebound.Simulation()
    sim.G = float(G)
    sim.integrator = "ias15"
    # REBOUND IAS15's epsilon is a relative accuracy parameter.
    try:
        sim.ri_ias15.epsilon = max(1e-14, min(1e-3, float(rtol)))
    except Exception:
        pass
    for i in range(3):
        sim.add(m=float(m[i]), x=float(p0[i, 0]), y=float(p0[i, 1]), z=float(p0[i, 2]),
                vx=float(v0[i, 0]), vy=float(v0[i, 1]), vz=float(v0[i, 2]))

    local = ThreeBodyEngine(m, r, p0, v0, G=float(G), softening=0.0,
                            collision=PASS, rtol=rtol, atol=atol)
    times = np.linspace(0.0, float(duration), samples)
    errors = []
    for target_t in times[1:]:
        sim.integrate(float(target_t), exact_finish_time=1)
        while local.t < target_t - 1e-13:
            local.step(min(0.05 * duration / (samples - 1), target_t - local.t), RK45)
        reference = np.array([[sim.particles[i].x, sim.particles[i].y, sim.particles[i].z]
                              for i in range(3)], dtype=float)
        errors.append(np.linalg.norm(local.pos - reference, axis=1))
    errors_arr = np.asarray(errors, dtype=float)
    rms = float(np.sqrt(np.mean(errors_arr**2)))
    max_err = float(np.max(errors_arr))
    pair_d = [np.linalg.norm(p0[j] - p0[i]) for i, j in ((0, 1), (0, 2), (1, 2))]
    scale = max(float(np.median(pair_d)), 1e-15)
    return ReboundComparison(
        duration=float(duration), samples=samples,
        rms_position_error=rms, max_position_error=max_err,
        characteristic_separation=scale, relative_rms_error=rms / scale,
        relative_max_error=max_err / scale,
    )
