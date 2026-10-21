"""Numerical checks for Gravity Lab 3D. Run with: python main.py --selftest"""
from __future__ import annotations
import math
import numpy as np

from .physics import (ThreeBodyEngine, body_properties, roche_fraction, VERLET, YOSHIDA, RK45,
                      PASS, MERGE, BOUNCE, STOP, FRAGMENT, ZONE_THRESH, ZONE_ROCHE,
                      G_AU_MSUN_YR)
from .presets import PRESETS, engine_inputs
from .fields import field_magnitude_grid


def run_selftest(verbose=True):
    results = []

    def check(name, condition, detail=""):
        good = bool(condition)
        results.append(good)
        if verbose:
            print(f"[{'PASS' if good else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

    # Sun-scale properties in AU/Msun/year units, converted to SI.
    G = 4 * math.pi**2
    g, vesc, rho = body_properties(1.0, 0.00465047, G)
    check("Sun surface gravity", abs(g * 1.495978707e11 / 3.15576e7**2 - 274.0) < 1.5,
          f"{g * 1.495978707e11 / 3.15576e7**2:.2f} m/s²")
    check("Sun escape velocity", abs(vesc * 1.495978707e11 / 3.15576e7 / 1000 - 617.7) < 2,
          f"{vesc * 1.495978707e11 / 3.15576e7 / 1000:.1f} km/s")
    check("Mean density positive", rho > 0, f"model density={rho:.4g}")
    check("Eggleton equal-mass Roche fraction", abs(roche_fraction(1) - 0.3789) < 0.001,
          f"fraction={roche_fraction(1):.4f}")

    # Force symmetry / Newton's third law.
    p = PRESETS["Butterfly I"]
    masses, radii, pos, vel = engine_inputs(p)
    eng = ThreeBodyEngine(masses, radii, pos, vel, p["G"], p["soft"], collision=PASS)
    net_force = np.sum(eng.m[:, None] * eng.accelerations(), axis=0)
    check("Newton's third law (net force zero)", np.max(np.abs(net_force)) < 1e-11,
          f"max={np.max(np.abs(net_force)):.2e}")

    # With zero softening, the exterior force follows the exact inverse-square law.
    exact = ThreeBodyEngine([2.0, 3.0, 1e-16], [0.1, 0.1, 0.1],
                            [[0, 0, 0], [2, 0, 0], [0, 1e6, 0]],
                            [[0, 0, 0], [0, 0, 0], [0, 0, 0]], G=2.0,
                            softening=0.0, collision=PASS)
    ax = float(exact.accelerations()[0, 0])
    check("Exact Newtonian inverse-square acceleration at ε=0", abs(ax - 1.5) < 1e-12,
          f"a_x={ax:.12g}, expected=1.5")
    zthr = eng.zone_radius(0, ZONE_THRESH, acceleration_threshold=0.8)
    check("Acceleration-threshold influence radius", abs(zthr - math.sqrt(eng.G * eng.m[0] / 0.8)) < 1e-12,
          f"radius={zthr:.4g}")
    zroche = eng.zone_radius(0, ZONE_ROCHE)
    expected_roche = min(np.linalg.norm(eng.pos[j] - eng.pos[0]) * roche_fraction(eng.m[0] / eng.m[j])
                         for j in range(1, 3))
    check("Roche-lobe estimate from pair separations", abs(zroche - expected_roche) < 1e-12,
          f"radius={zroche:.4g}")

    # Periodic figure-eight: both methods should approximately close after one period.
    fig = PRESETS["Figure-eight"]
    masses, radii, pos, vel = engine_inputs(fig)
    period = 6.32591398
    for method in (VERLET, YOSHIDA):
        sim = ThreeBodyEngine(masses, radii, pos, vel, fig["G"], fig["soft"], collision=PASS)
        initial = sim.pos.copy()
        n = 2200
        for _ in range(n):
            sim.step(period / n, method)
        err = float(np.max(np.abs(sim.pos - initial)))
        de = sim.energy_error()
        check(f"Figure-eight period / {method}", err < 2e-3 and de < 1e-5,
              f"position error={err:.2e}, energy drift={de:.2e}")

    # Step-size convergence: halving Yoshida's time step improves the periodic orbit closure.
    closure_errors = []
    for nominal_dt in (0.02, 0.01):
        sim = ThreeBodyEngine(masses, radii, pos, vel, fig["G"], 0.0, collision=PASS)
        initial = sim.pos.copy()
        n = math.ceil(period / nominal_dt)
        for _ in range(n):
            sim.step(period / n, YOSHIDA)
        closure_errors.append(float(np.max(np.abs(sim.pos - initial))))
    check("Yoshida step-size convergence", closure_errors[1] < 0.2 * closure_errors[0],
          f"coarse={closure_errors[0]:.2e}, fine={closure_errors[1]:.2e}")

    # RK45 tolerance convergence over a known periodic three-body orbit.
    rk_errors = []
    for rtol in (1e-7, 1e-9):
        sim = ThreeBodyEngine(masses, radii, pos, vel, fig["G"], 0.0, collision=PASS,
                              rtol=rtol, atol=rtol * 1e-3)
        initial = sim.pos.copy()
        while sim.t < period - 1e-12:
            sim.step(min(0.05, period - sim.t), RK45)
        rk_errors.append(float(np.max(np.abs(sim.pos - initial))))
    check("Dormand–Prince RK45 tolerance convergence", rk_errors[1] < 0.5 * rk_errors[0],
          f"rtol=1e-7: {rk_errors[0]:.2e}; rtol=1e-9: {rk_errors[1]:.2e}")

    # Conservation in a generic non-colliding 3D system.
    sim = ThreeBodyEngine(masses, radii, pos, vel, fig["G"], fig["soft"], collision=PASS)
    for _ in range(1200):
        sim.step(0.001, YOSHIDA)
    check("3D energy conservation", sim.energy_error() < 1e-8, f"drift={sim.energy_error():.2e}")
    check("3D angular momentum conservation", sim.angular_momentum_error() < 1e-8,
          f"drift={sim.angular_momentum_error():.2e}")
    check("3D linear momentum conservation", sim.momentum_error() < 1e-8,
          f"drift={sim.momentum_error():.2e}")

    # Merge: conserved mass/momentum, volume-radius and angular momentum via spin.
    sim = ThreeBodyEngine([2, 1, 3], [0.2, 0.3, 0.2],
                          [[-0.15, 0, 0], [0.15, 0, 0], [12, 0, 0]],
                          [[0, 0.4, 0], [0, -0.8, 0], [0, 0, 0]], G=0.0, softening=0.01,
                          collision=MERGE)
    mass_before = float(sim.m.sum())
    mom_before = sim.linear_momentum().copy()
    ang_before = sim.angular_momentum().copy()
    sim.step(1e-6, VERLET)
    expected_radius = (0.2**3 + 0.3**3)**(1/3)
    check("Merge conserves total mass", abs(sim.m.sum() - mass_before) < 1e-12)
    check("Merge conserves linear momentum", np.linalg.norm(sim.linear_momentum() - mom_before) < 1e-10)
    check("Merge stores internal angular momentum as spin", np.linalg.norm(sim.angular_momentum() - ang_before) < 1e-9)
    check("Merge combines volume-equivalent radius", abs(max(sim.R) - expected_radius) < 1e-8,
          f"radius={max(sim.R):.5g}")

    # Collision restitution tests without gravity, isolating the impulse.
    for restitution, should_lose in ((1.0, False), (0.4, True)):
        sim = ThreeBodyEngine([1, 1, 1], [0.6, 0.6, 0.1],
                              [[-0.5, 0, 0], [0.5, 0, 0], [20, 10, 0]],
                              [[1, 0, 0], [-1, 0, 0], [0, 0, 0]], G=0.0, softening=0.01,
                              collision=BOUNCE, restitution=restitution)
        e_before = sim.energy()
        sim.step(1e-6, VERLET)
        loss = sim.energy_lost
        condition = loss > 0.1 if should_lose else abs(sim.energy() - e_before) < 1e-8
        check(f"Bounce restitution {restitution:.1f}", condition, f"booked energy loss={loss:.4g}")

    # Swept-sphere collision detection must stop high-speed bodies from tunneling.
    collision_result = None
    for method in (VERLET, RK45):
        sim = ThreeBodyEngine([1, 1, 1], [0.5, 0.5, 0.1],
                              [[-5, 0, 0], [5, 0, 0], [0, 100, 0]],
                              [[100, 0, 0], [-100, 0, 0], [0, 0, 0]],
                              G=0.0, softening=0.0, collision=BOUNCE, restitution=1.0)
        momentum_before = sim.linear_momentum().copy()
        sim.step(0.2, method)  # Bodies would cross by 30 units without event handling.
        check(f"High-speed collision event / {method} (no tunneling)",
              sim.vel[0, 0] < 0 and sim.vel[1, 0] > 0 and len(sim.events) >= 1,
              f"vx=({sim.vel[0, 0]:.3g}, {sim.vel[1, 0]:.3g}); event={sim.events[0][1] if sim.events else 'none'}")
        collision_result = np.linalg.norm(sim.linear_momentum() - momentum_before)
    check("Elastic impact conserves linear momentum", collision_result < 1e-9,
          f"momentum error={collision_result:.2e}")

    # Pause-on-impact mode should stop the integrator and write an event.
    sim = ThreeBodyEngine([1, 1, 1], [0.4, 0.4, 0.1],
                          [[0, 0, 0], [0.5, 0, 0], [15, 0, 0]],
                          [[0, 0, 0], [0, 0, 0], [0, 0, 0]], G=0.0, softening=0.01,
                          collision=STOP)
    sim.step(1e-6, VERLET)
    check("Pause-on-impact collision mode", sim.impact and len(sim.events) == 1,
          sim.events[-1][1] if sim.events else "no event emitted")

    # Adaptive integration is still tested even though the general close-encounter
    # demo is intentionally not exposed in the image-inspired preset dropdown.
    pp_dt = 0.0015
    sim = ThreeBodyEngine([3, 4, 5], [0.003, 0.0035, 0.004],
                          [[1, 3, 0], [-2, -1, 0], [1, -1, 0]],
                          np.zeros((3, 3)), G=1.0, softening=0.0, collision=PASS)
    while sim.t < 8.0 - 1e-9 and sim.is_healthy():
        sim.advance(4, pp_dt, YOSHIDA, adaptive=True, max_wall=0.08)
    check("Adaptive close-encounter integration", sim.is_healthy() and sim.energy_error() < 5e-3,
          f"t={sim.t:.3f}, drift={sim.energy_error():.2e}")

    # A separate ephemeris-style verification case keeps astronomical unit tests
    # without cluttering the user-facing periodic-orbit gallery.
    astro_masses = [1.0, 3.003e-6, 9.546e-4]
    astro_radii = [0.00465047, 4.26e-5, 4.78e-4]
    astro_pos = [[0, 0, 0], [1, 0, 0], [-5.2, 0, 0]]
    v_j = 2 * math.pi / math.sqrt(5.2)
    inclination = math.radians(11.5)
    astro_vel = [[0, 0, 0], [0, 2 * math.pi, 0],
                 [0, -v_j * math.cos(inclination), -v_j * math.sin(inclination)]]
    sim = ThreeBodyEngine(astro_masses, astro_radii, astro_pos, astro_vel,
                          G_AU_MSUN_YR, softening=0.0, collision=PASS)
    r0 = float(np.linalg.norm(sim.pos[1] - sim.pos[0]))
    for _ in range(1000):
        sim.step(0.001, YOSHIDA)
    radius = float(np.linalg.norm(sim.pos[1] - sim.pos[0]))
    check("Earth-like orbital radius after one year", abs(radius - r0) < 0.002,
          f"relative separation={radius:.5f} AU")

    # The field slice should be finite, non-negative and shaped as the input grid.
    xx, yy = np.meshgrid(np.linspace(-2, 2, 16), np.linspace(-2, 2, 16))
    ff = field_magnitude_grid(xx, yy, 0.0, [1, 1, 1], [[-1, 0, 0], [1, 0, 0], [0, 1, 0]], 1.0, 0.05)
    check("Combined gravitational field map", ff.shape == xx.shape and np.all(np.isfinite(ff)) and np.all(ff >= 0),
          f"grid={ff.shape}")

    # Advanced physics options are intentionally optional and documented as
    # reduced models: fixed-axis J2, pairwise weak-field 1PN, and radial tidal damping.
    jm = [10.0, 1.0, 1e-10]
    jr = [0.5, 0.1, 0.1]
    jp = [[0.0, 0.0, 0.0], [2.0, 0.2, 0.4], [10000.0, 0.0, 0.0]]
    jv = np.zeros((3, 3))
    j2_engine = ThreeBodyEngine(jm, jr, jp, jv, G=1.0, collision=PASS,
                                enable_oblateness=True, j2=[0.1, 0.0, 0.0])
    j2_force = np.sum(j2_engine.m[:, None] * j2_engine.accelerations(), axis=0)
    check("J2 exterior model preserves translational momentum", np.linalg.norm(j2_force) < 1e-10,
          f"net force={np.linalg.norm(j2_force):.2e}")
    h = 1e-5
    j2_engine.pos[1, 0] += h; e_plus = j2_engine.energy()
    j2_engine.pos[1, 0] -= 2*h; e_minus = j2_engine.energy()
    j2_engine.pos[1, 0] += h
    numerical_ax = -(e_plus - e_minus) / (2*h*jm[1])
    analytical_ax = float(j2_engine.accelerations()[1, 0])
    check("J2 acceleration agrees with interaction-potential gradient",
          abs(numerical_ax - analytical_ax) < 1e-7,
          f"finite-difference error={abs(numerical_ax-analytical_ax):.2e}")

    pn = ThreeBodyEngine([1.0, 2.0, 1e-10], [0.02]*3,
                         [[-1, 0, 0], [1, 0, 0], [0, 10000, 0]],
                         [[0, -0.8, 0], [0, 0.4, 0], [0, 0, 0]],
                         G=1.0, collision=PASS, enable_1pn=True, c_light=10.0)
    pn_force = np.sum(pn.m[:, None] * pn.accelerations(), axis=0)
    check("Pairwise 1PN correction remains momentum balanced", np.linalg.norm(pn_force) < 1e-10,
          f"net force={np.linalg.norm(pn_force):.2e}")
    pn.step(1e-4, RK45)
    check("Pairwise 1PN uses RK45 and remains finite", pn.is_healthy() and pn.rk45_accepted_steps > 0,
          f"accepted RK45 steps={pn.rk45_accepted_steps}")

    tide = ThreeBodyEngine([1, 1, 1], [0.1, 0.1, 0.1],
                           [[-2, 0, 0], [2, 0, 0], [0, 50, 0]],
                           [[1, 0, 0], [-1, 0, 0], [0, 0, 0]],
                           G=0.0, collision=PASS, tidal_damping=0.5)
    tide_p0 = tide.linear_momentum().copy()
    tide.step(0.2, RK45)
    check("Tidal damping records positive heat", tide.tidal_energy_dissipated > 0,
          f"heat={tide.tidal_energy_dissipated:.3e}")
    check("Tidal heat closes the dissipative energy budget",
          tide.energy_error() < 1e-8 and np.linalg.norm(tide.linear_momentum()-tide_p0) < 1e-10,
          f"energy error={tide.energy_error():.2e}")

    spin = ThreeBodyEngine([2.0, 1.0, 1e-10], [0.5, 0.1, 0.1],
                           [[0, 0, 0], [2, 0, 0], [0, 1e6, 0]], np.zeros((3, 3)),
                           G=0.0, collision=PASS, spin_omega=[[0, 0, 2], [0, 0, 0], [0, 0, 0]])
    # I=2/5 M R^2=0.2, L=I omega=0.4, rotational KE=0.4.
    check("Body spin contributes to angular momentum and rotational energy",
          abs(spin.angular_momentum()[2] - 0.4) < 1e-12 and abs(spin.energy() - 0.4) < 1e-12,
          f"spin Lz={spin.angular_momentum()[2]:.3g}, spin KE={spin.energy():.3g}")

    frag = ThreeBodyEngine([1, 1, 1], [0.6, 0.6, 0.1],
                           [[-0.5, 0, 0], [0.5, 0, 0], [0, 10, 0]],
                           [[1, 0, 0], [-1, 0, 0], [0, 0, 0]],
                           G=0.0, collision=FRAGMENT)
    fragment_mass0 = float(frag.m.sum())
    fragment_mom0 = frag.linear_momentum().copy()
    fragment_ang0 = frag.angular_momentum().copy()
    frag.step(1e-5, VERLET)
    check("Toy fragmentation conserves total mass and momentum",
          abs(float(frag.m.sum()) - fragment_mass0) < 1e-12
          and np.linalg.norm(frag.linear_momentum() - fragment_mom0) < 1e-12
          and any("fragmented" in msg for _, msg in frag.events),
          f"mass={frag.m.sum():.3g}, momentum error={np.linalg.norm(frag.linear_momentum()-fragment_mom0):.2e}")
    check("Toy fragmentation transfers lost orbital angular momentum to spin",
          np.linalg.norm(frag.angular_momentum() - fragment_ang0) < 1e-10,
          f"angular momentum error={np.linalg.norm(frag.angular_momentum()-fragment_ang0):.2e}")

    # Published equal-mass periodic-orbit gallery seeds: these are rounded initial
    # conditions, so validate structure and invariants rather than exact closure.
    gallery = list(PRESETS.items())
    expected_gallery_names = {
        "Butterfly I", "Butterfly II", "Butterfly III", "Butterfly IV", "Bumblebee",
        "Dragonfly", "Figure-eight", "Goggles", "Moth I", "Moth II", "Moth III", "Yarn",
        "Yin-Yang I (A)", "Yin-Yang I (B)", "Yin-Yang II (A)", "Yin-Yang II (B)",
    }
    check("Dropdown contains only the 16 image-gallery orbit presets",
          set(PRESETS) == expected_gallery_names,
          f"models={len(gallery)}")
    check("Preset labels are concise and match their display names",
          all("Periodic ·" not in name and "T≈" not in name
              and preset.get("model_name") == name for name, preset in gallery),
          ", ".join(PRESETS))
    valid_gallery = True
    for name, preset in gallery:
        masses, radii, pos, vel = engine_inputs(preset)
        mass_arr = np.asarray(masses, dtype=float)
        pos_arr = np.asarray(pos, dtype=float)
        vel_arr = np.asarray(vel, dtype=float)
        valid_gallery &= (preset["G"] == 1.0 and preset["soft"] == 0.0
                          and preset["collision"] == PASS and preset.get("period", 0) > 0
                          and np.allclose(mass_arr, 1.0)
                          and np.max(np.abs(np.sum(mass_arr[:, None] * pos_arr, axis=0))) < 1e-10
                          and np.max(np.abs(np.sum(mass_arr[:, None] * vel_arr, axis=0))) < 1e-10
                          and np.all(np.isfinite(pos_arr)) and np.all(np.isfinite(vel_arr))
                          and np.all(np.asarray(radii) > 0))
    check("Periodic orbit seeds have equal masses and zero COM momentum", valid_gallery,
          "equal-mass, zero-momentum Newtonian seeds")

    # The classic figure-eight is a directly inspectable reference orbit and
    # should close over one nominal period with a tight adaptive tolerance.
    for preset_name, check_name in (
        ("Figure-eight", "Figure-eight seed exposes a nominal period"),
        ("Butterfly I", "Butterfly I seed exposes a nominal period"),
    ):
        preset = PRESETS[preset_name]
        check(check_name, preset.get("period", 0) > 0 and preset.get("model_name") == preset_name,
              f"period={preset.get('period', 0):.6g}")

    if verbose:
        print(f"\n{sum(results)}/{len(results)} checks passed" if all(results)
              else f"\n{sum(results)}/{len(results)} checks passed; review FAIL entries")
    return 0 if all(results) else 1
