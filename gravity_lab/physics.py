"""3D Newtonian three-body engine with finite-radius collision modes.

The default force model is exact Newtonian point-mass gravity outside contact.
Optional Plummer softening is retained for experimentation, but any nonzero
softening changes the force law. Finite-radius collisions use event-aware
stepping with swept-segment detection, and Dormand–Prince RK45 provides an
error-controlled adaptive alternative to the symplectic integrators.
"""
from __future__ import annotations

from collections import deque
import math
import time
from typing import Iterable

import numpy as np

VERLET = "Velocity Verlet (2nd order)"
YOSHIDA = "Yoshida (4th order, symplectic)"
RK45 = "Dormand–Prince RK45 (adaptive)"
INTEGRATORS = (YOSHIDA, VERLET, RK45)
MERGE = "Merge (inelastic)"
BOUNCE = "Bounce"
PASS = "Pass through"
STOP = "Pause on impact"
FRAGMENT = "Fragment (simplified two-remnant model)"
COLLISION_MODES = (MERGE, BOUNCE, PASS, STOP, FRAGMENT)
ZONE_ROCHE = "Roche lobe (Eggleton)"
ZONE_THRESH = "Gravity threshold"
ZONE_MODES = (ZONE_THRESH, ZONE_ROCHE)
PAIRS = ((0, 1), (0, 2), (1, 2))

# Internal SI conversions for astronomical-unit / solar-mass / year units.
AU_M = 1.495978707e11
YEAR_S = 3.15576e7
MSUN_KG = 1.98847e30
AU_KM = AU_M / 1000.0
G_SI = 6.67430e-11
G_AU_MSUN_YR = G_SI * MSUN_KG * YEAR_S**2 / AU_M**3
C_AU_PER_YEAR = 299792458.0 * YEAR_S / AU_M


def body_properties(mass: float, radius: float, G: float) -> tuple[float, float, float]:
    """Return surface gravity, escape speed and mean density in model units."""
    if mass <= 0 or radius <= 0 or G < 0:
        raise ValueError("Mass and radius must be positive; G must be non-negative.")
    g = G * mass / radius**2
    vesc = math.sqrt(2.0 * G * mass / radius)
    rho = mass / ((4.0 / 3.0) * math.pi * radius**3)
    return g, vesc, rho


def roche_fraction(q: float) -> float:
    """Eggleton approximation to Roche-lobe radius / separation for mass ratio q."""
    if not math.isfinite(q) or q <= 0:
        return 0.0
    q13 = q ** (1.0 / 3.0)
    q23 = q13 * q13
    return 0.49 * q23 / (0.6 * q23 + math.log1p(q13))


class ThreeBodyEngine:
    """Three-body integrator in 3D with adaptive stepping and collision handling."""

    _W1 = 1.0 / (2.0 - 2.0 ** (1.0 / 3.0))
    _W0 = -(2.0 ** (1.0 / 3.0)) * _W1
    _C = (_W1 / 2, (_W0 + _W1) / 2, (_W0 + _W1) / 2, _W1 / 2)
    _D = (_W1, _W0, _W1)

    def __init__(self, masses: Iterable[float], radii: Iterable[float], positions,
                 velocities, G: float = 1.0, softening: float = 0.0,
                 collision: str = MERGE, restitution: float = 1.0,
                 rtol: float = 1e-9, atol: float = 1e-12,
                 *, enable_oblateness: bool = False, j2=None, spin_axes=None, spin_omega=None,
                 enable_1pn: bool = False, c_light: float = 1000.0,
                 tidal_damping: float = 0.0):
        self.m = np.asarray(masses, dtype=float).reshape(3).copy()
        self.R = np.asarray(radii, dtype=float).reshape(3).copy()
        self.pos = np.asarray(positions, dtype=float).reshape(3, 3).copy()
        self.vel = np.asarray(velocities, dtype=float).reshape(3, 3).copy()
        self.G = float(G)
        self.softening = float(softening)
        self.eps2 = self.softening**2
        self.collision = collision
        self.restitution = float(restitution)
        if np.any(self.m <= 0) or np.any(self.R <= 0):
            raise ValueError("All initial masses and radii must be positive.")
        if self.softening == 0.0:
            for i, j in PAIRS:
                if np.array_equal(self.pos[i], self.pos[j]):
                    raise ValueError("With exact Newtonian gravity (softening=0), two bodies cannot start at the exact same position.")
        if not (np.all(np.isfinite(self.pos)) and np.all(np.isfinite(self.vel))):
            raise ValueError("Positions and velocities must be finite.")
        if self.G < 0 or self.softening < 0:
            raise ValueError("G and softening must be non-negative.")
        if collision not in COLLISION_MODES:
            raise ValueError(f"Unknown collision mode: {collision}")
        self.restitution = min(1.0, max(0.0, self.restitution))
        self.enable_oblateness = bool(enable_oblateness)
        self.j2 = np.zeros(3, dtype=float) if j2 is None else np.asarray(j2, dtype=float).reshape(3).copy()
        axes = np.tile(np.array([0.0, 0.0, 1.0]), (3, 1)) if spin_axes is None else np.asarray(spin_axes, dtype=float).reshape(3, 3).copy()
        if not np.all(np.isfinite(self.j2)) or not np.all(np.isfinite(axes)):
            raise ValueError("J2 coefficients and spin axes must be finite.")
        axis_norms = np.linalg.norm(axes, axis=1)
        if np.any(axis_norms <= 1e-15):
            raise ValueError("Each spin axis must be a non-zero 3D vector.")
        self.spin_axes = axes / axis_norms[:, None]
        self.enable_1pn = bool(enable_1pn)
        self.c_light = float(c_light)
        self.tidal_damping = float(tidal_damping)
        if not math.isfinite(self.c_light) or self.c_light <= 0:
            raise ValueError("Speed of light in model units must be finite and positive.")
        if not math.isfinite(self.tidal_damping) or self.tidal_damping < 0:
            raise ValueError("Tidal radial-damping coefficient must be finite and non-negative.")
        self.tidal_energy_dissipated = 0.0
        self.rtol = float(rtol)
        self.atol = float(atol)
        if not (math.isfinite(self.rtol) and 0 < self.rtol < 1):
            raise ValueError("RK45 relative tolerance must be finite and between 0 and 1.")
        if not (math.isfinite(self.atol) and self.atol > 0):
            raise ValueError("RK45 absolute tolerance must be finite and positive.")
        self.rk45_last_error = 0.0
        self.rk45_accepted_steps = 0
        self.rk45_rejected_steps = 0
        self.alive = np.ones(3, dtype=bool)
        self.spin_omega = np.zeros((3, 3), dtype=float) if spin_omega is None else np.asarray(spin_omega, dtype=float).reshape(3, 3).copy()
        if not np.all(np.isfinite(self.spin_omega)):
            raise ValueError("Spin angular velocities must be finite.")
        if spin_axes is None:
            for i in range(3):
                rate = float(np.linalg.norm(self.spin_omega[i]))
                if rate > 1e-15:
                    self.spin_axes[i] = self.spin_omega[i] / rate
        # Uniform-sphere inertia is a documented approximation for rotational
        # energy/angular momentum. Spin axes are fixed unless a collision changes
        # the remnant's angular momentum; torque-driven precession is not modeled.
        inertia = 0.4 * self.m * self.R**2
        self.spin = inertia[:, None] * self.spin_omega
        self._refresh_mask()
        self.t = 0.0
        self._acc = None
        self.events: deque[tuple[float, str]] = deque(maxlen=500)
        self.impact = False
        self._touching: set[tuple[int, int]] = set()
        self.energy_lost = 0.0
        self.e0 = self.energy()
        self.p0 = self.linear_momentum().copy()
        self.l0 = self.angular_momentum().copy()

    def _refresh_mask(self):
        self._ok = np.outer(self.alive, self.alive) & ~np.eye(3, dtype=bool)

    def _accelerations_newtonian_pairs(self, positions: np.ndarray) -> np.ndarray:
        """Allocation-light symmetric pair accumulation for the Newtonian model."""
        p = positions
        acc = np.zeros((3, 3), dtype=float)
        for i, j in PAIRS:
            if not (self.alive[i] and self.alive[j]):
                continue
            dx = float(p[j, 0] - p[i, 0])
            dy = float(p[j, 1] - p[i, 1])
            dz = float(p[j, 2] - p[i, 2])
            r2 = dx * dx + dy * dy + dz * dz
            if self.softening == 0.0 and r2 == 0.0:
                raise FloatingPointError(
                    "Two active point masses became coincident. Reduce the time step or enable encounter-aware stepping."
                )
            inv_r3 = (r2 + self.eps2) ** -1.5
            scale_i = self.G * self.m[j] * inv_r3
            scale_j = self.G * self.m[i] * inv_r3
            acc[i, 0] += scale_i * dx
            acc[i, 1] += scale_i * dy
            acc[i, 2] += scale_i * dz
            acc[j, 0] -= scale_j * dx
            acc[j, 1] -= scale_j * dy
            acc[j, 2] -= scale_j * dz
        return acc

    def accelerations(self, pos=None, vel=None) -> np.ndarray:
        """Compute Newtonian gravity plus explicitly enabled correction models.

        J2 is a fixed-spin-axis zonal-harmonic approximation for exterior fields.
        The 1PN option is a pairwise two-body correction, not the full N-body
        Einstein–Infeld–Hoffmann equations. Tides are a radial-damping surrogate,
        not a full equilibrium-tide/spin-orbit evolution model.
        """
        p = self.pos if pos is None else np.asarray(pos, dtype=float)
        # The default Newtonian path is the hot loop for ordinary simulations.
        # For three bodies, accumulating each active pair directly avoids several
        # small broadcast/einsum temporaries per force evaluation. Keep the
        # vectorized implementation below for advanced correction models.
        if not (self.enable_oblateness or self.enable_1pn or self.tidal_damping > 0.0):
            return self._accelerations_newtonian_pairs(p)
        v = self.vel if vel is None else np.asarray(vel, dtype=float)
        d_to_source = p[None, :, :] - p[:, None, :]  # target i -> source j
        dist2 = np.einsum("ijk,ijk->ij", d_to_source, d_to_source)
        if self.softening == 0.0 and np.any(self._ok & (dist2 == 0.0)):
            raise FloatingPointError(
                "Two active point masses became coincident. Reduce the time step or enable encounter-aware stepping."
            )
        r2 = dist2 + self.eps2
        r2 = np.where(self._ok, r2, 1.0)
        inv_r3 = np.where(self._ok, r2 ** -1.5, 0.0)
        acc = self.G * np.einsum("ij,j,ijk->ik", inv_r3, self.m, d_to_source)

        # Oblate-source J2 perturbation. r points from each source j to target i.
        if self.enable_oblateness and self.G > 0:
            for i in range(3):
                if not self.alive[i]:
                    continue
                for j in range(3):
                    if i == j or not self.alive[j] or self.j2[j] == 0.0:
                        continue
                    rvec = p[i] - p[j]
                    rr2 = float(rvec @ rvec)
                    if rr2 <= 0.0:
                        continue
                    rr = math.sqrt(rr2)
                    # J2 is an exterior-field model. Internal fields are not
                    # represented by this point-mass + quadrupole approximation.
                    if rr < self.R[j]:
                        continue
                    axis = self.spin_axes[j]
                    z = float(rvec @ axis)
                    correction = (1.5 * self.G * self.m[j] * self.j2[j] * self.R[j]**2 / rr**5) * (
                        (5.0 * z*z / rr2 - 1.0) * rvec - 2.0*z*axis
                    )
                    acc[i] += correction
                    # The same pair potential produces an equal-and-opposite
                    # reaction force on the extended source. Spin-axis torque
                    # and precession are intentionally omitted, but COM momentum
                    # remains conserved by this translational reaction term.
                    acc[j] -= (self.m[i] / self.m[j]) * correction

        # Pairwise 1PN (post-Newtonian) correction. Valid as a useful weak-field
        # approximation, but not a substitute for full N-body EIH dynamics.
        if self.enable_1pn and self.G > 0:
            c2 = self.c_light * self.c_light
            for i, j in PAIRS:
                if not (self.alive[i] and self.alive[j]):
                    continue
                rvec = p[i] - p[j]
                rr2 = float(rvec @ rvec)
                if rr2 <= 0:
                    continue
                rr = math.sqrt(rr2)
                n = rvec / rr
                vrel = v[i] - v[j]
                v2 = float(vrel @ vrel)
                vr = float(n @ vrel)
                total_mass = self.m[i] + self.m[j]
                eta = self.m[i] * self.m[j] / (total_mass * total_mass)
                gm_over_r = self.G * total_mass / rr
                bracket = n * ((4.0 + 2.0*eta)*gm_over_r - (1.0 + 3.0*eta)*v2
                               + 1.5*eta*vr*vr) + (4.0 - 2.0*eta)*vr*vrel
                relative_correction = (self.G * total_mass / (rr2*c2)) * bracket
                acc[i] += (self.m[j] / total_mass) * relative_correction
                acc[j] -= (self.m[i] / total_mass) * relative_correction

        # Phenomenological radial tidal lag: damps relative radial motion and
        # records the removed mechanical energy as heat. It does not model full
        # spin synchronization, Love-number response, or tidal bulges.
        if self.tidal_damping > 0.0:
            for i, j in PAIRS:
                if not (self.alive[i] and self.alive[j]):
                    continue
                rvec = p[i] - p[j]
                rr = float(np.linalg.norm(rvec))
                if rr <= 1e-15:
                    continue
                n = rvec / rr
                vrel = v[i] - v[j]
                vr = float(vrel @ n)
                total_mass = self.m[i] + self.m[j]
                relative_tide = -self.tidal_damping * vr * n
                acc[i] += (self.m[j] / total_mass) * relative_tide
                acc[j] -= (self.m[i] / total_mass) * relative_tide
        return acc

    def pair_distances(self) -> np.ndarray:
        values = np.full(3, np.nan)
        for k, (i, j) in enumerate(PAIRS):
            if self.alive[i] and self.alive[j]:
                values[k] = np.linalg.norm(self.pos[j] - self.pos[i])
        return values

    def energy(self) -> float:
        live_m = np.where(self.alive, self.m, 0.0)
        ke = 0.5 * float(np.sum(live_m * np.einsum("ik,ik->i", self.vel, self.vel)))
        # Spin angular momentum is a resolved body property; assume uniform-sphere
        # moment of inertia I = 2/5 MR². Zero spin leaves the original model unchanged.
        inertia = 0.4 * self.m * self.R**2
        spin_ke = 0.0
        for i in range(3):
            if self.alive[i] and inertia[i] > 0:
                spin_ke += float(self.spin[i] @ self.spin[i]) / (2.0 * inertia[i])
        ke += spin_ke
        pe = 0.0
        for i, j in PAIRS:
            if self.alive[i] and self.alive[j]:
                d = self.pos[j] - self.pos[i]
                rr2 = float(d @ d)
                rr = math.sqrt(rr2 + self.eps2)
                pe -= self.G * self.m[i] * self.m[j] / rr
                if self.enable_oblateness and rr2 > 0.0:
                    rvec = self.pos[j] - self.pos[i]
                    for source, target in ((i, j), (j, i)):
                        if self.j2[source] == 0.0 or math.sqrt(rr2) < self.R[source]:
                            continue
                        z = float(rvec @ self.spin_axes[source]) if source == i else float((-rvec) @ self.spin_axes[source])
                        p2 = 0.5 * (3.0 * z*z / rr2 - 1.0)
                        pe += (self.G * self.m[i] * self.m[j] * self.j2[source] * self.R[source]**2
                               / (rr**3) * p2)
        return ke + pe

    def linear_momentum(self) -> np.ndarray:
        live_m = np.where(self.alive, self.m, 0.0)
        return np.sum(live_m[:, None] * self.vel, axis=0)

    def angular_momentum(self) -> np.ndarray:
        live_m = np.where(self.alive, self.m, 0.0)
        orbital = np.sum(live_m[:, None] * np.cross(self.pos, self.vel), axis=0)
        return orbital + np.sum(self.spin[self.alive], axis=0)

    def center_of_mass(self) -> np.ndarray:
        live_m = np.where(self.alive, self.m, 0.0)
        total = float(live_m.sum())
        return np.sum(live_m[:, None] * self.pos, axis=0) / max(total, 1e-300)

    def center_velocity(self) -> np.ndarray:
        live_m = np.where(self.alive, self.m, 0.0)
        return np.sum(live_m[:, None] * self.vel, axis=0) / max(float(live_m.sum()), 1e-300)

    def energy_error(self) -> float:
        expected = self.e0 - self.energy_lost - self.tidal_energy_dissipated
        return abs(self.energy() - expected) / max(abs(self.e0), 1e-30)

    def angular_momentum_error(self) -> float:
        ref = float(np.linalg.norm(self.l0))
        current = float(np.linalg.norm(self.angular_momentum() - self.l0))
        return current / ref if ref > 1e-12 else current

    def momentum_error(self) -> float:
        ref = float(np.linalg.norm(self.p0))
        delta = float(np.linalg.norm(self.linear_momentum() - self.p0))
        return delta / ref if ref > 1e-12 else delta

    def is_healthy(self) -> bool:
        return bool(np.all(np.isfinite(self.pos)) and np.all(np.isfinite(self.vel))
                    and np.max(np.abs(self.pos)) < 1e10 and np.all(np.isfinite(self.m)))

    def surface_properties(self, i: int) -> tuple[float, float, float]:
        if not self.alive[i]:
            return math.nan, math.nan, math.nan
        return body_properties(float(self.m[i]), float(self.R[i]), self.G)

    def zone_radius(self, i: int, mode: str = ZONE_THRESH,
                    acceleration_threshold: float = 0.2) -> float:
        if not self.alive[i]:
            return math.nan
        if mode == ZONE_THRESH:
            if acceleration_threshold > 0 and self.G > 0:
                return math.sqrt(self.G * self.m[i] / acceleration_threshold)
            return math.nan
        if mode == ZONE_ROCHE:
            candidates = []
            for j in range(3):
                if i != j and self.alive[j] and self.m[j] > 0:
                    separation = float(np.linalg.norm(self.pos[j] - self.pos[i]))
                    candidates.append(separation * roche_fraction(self.m[i] / self.m[j]))
            return min(candidates) if candidates else math.nan
        raise ValueError(f"Unknown zone mode: {mode}")

    def timescale(self) -> float:
        tau = math.inf
        for i, j in PAIRS:
            if not (self.alive[i] and self.alive[j]):
                continue
            delta = self.pos[j] - self.pos[i]
            r = math.sqrt(float(delta @ delta) + self.eps2)
            dv = self.vel[j] - self.vel[i]
            speed = float(np.linalg.norm(dv))
            if self.G > 0:
                tau = min(tau, math.sqrt(r**3 / (self.G * (self.m[i] + self.m[j]))))
            if speed > 0:
                tau = min(tau, r / speed)
                if self.collision != PASS:
                    clearance = r - (self.R[i] + self.R[j])
                    tau = min(tau, max(clearance, 0.02 * (self.R[i] + self.R[j])) / speed)
        return tau

    def step(self, h: float, method: str = YOSHIDA):
        """Advance exactly ``h`` model-time units, resolving finite-radius impacts.

        Collision time is first estimated from relative position/velocity. The
        stepper approaches predicted contact with smaller substeps, then uses a
        swept-segment check as a fallback for curved trajectories. The contact
        time is approximate for accelerated paths, so adaptive RK45 is preferred
        for difficult close encounters.
        """
        if h <= 0 or not math.isfinite(h):
            raise ValueError("Time step must be finite and positive.")
        if method not in INTEGRATORS:
            raise ValueError(f"Unknown integrator: {method}")
        if (self.enable_1pn or self.tidal_damping > 0.0) and method != RK45:
            raise ValueError("The velocity-dependent 1PN/tidal options require Dormand–Prince RK45. Select RK45 or disable those corrections.")
        if self.impact:
            return

        remaining = float(h)
        processed = 0
        # Handles multiple impacts in one outer step without freezing animation.
        while remaining > max(1e-14, h * 1e-13) and processed < 16:
            if self.collision != PASS:
                pair, toi = self._earliest_contact_time()
                if pair is not None and toi <= remaining:
                    # Approach contact in successively smaller intervals so the
                    # force integrator does not leap through the physical surface.
                    event_floor = max(h * 1e-7, 1e-13)
                    if toi > event_floor and toi < remaining * 0.5:
                        sub = max(0.5 * toi, event_floor)
                        self._integrate_interval(sub, method)
                        self.t += sub
                        remaining -= sub
                        continue
                    if toi > 0.0:
                        self._integrate_interval(toi, method)
                        self.t += toi
                        remaining -= toi
                    i, j = pair
                    separation = float(np.linalg.norm(self.pos[j] - self.pos[i]))
                    contact = self.R[i] + self.R[j]
                    if separation < contact * (1.0 - 1e-10):
                        # User-supplied or pre-existing overlap: resolve in place.
                        # Snapping from an already-overlapping configuration would
                        # introduce an unnecessary angular-momentum impulse.
                        self._resolve_collision_pair(i, j)
                    else:
                        self._snap_to_contact(i, j)
                        self._resolve_collision_pair(i, j)
                    self._acc = None
                    processed += 1
                    if self.impact:
                        return
                    continue

            start_pos = self.pos.copy()
            start_vel = self.vel.copy()
            start_alive = self.alive.copy()
            self._integrate_interval(remaining, method)
            hit = None if self.collision == PASS else self._swept_first_contact(
                start_pos, self.pos, start_alive
            )
            if hit is not None:
                pair, fraction = hit
                # Rewind and integrate to the interpolated first-contact time.
                self.pos = start_pos
                self.vel = start_vel
                self._acc = None
                hit_dt = max(0.0, min(remaining, remaining * fraction))
                if hit_dt > max(h * 1e-13, 1e-14):
                    self._integrate_interval(hit_dt, method)
                    self.t += hit_dt
                remaining -= hit_dt
                self._snap_to_contact(*pair)
                self._resolve_collision_pair(*pair)
                self._acc = None
                processed += 1
                if self.impact:
                    return
                continue

            self.t += remaining
            remaining = 0.0

        if remaining > max(1e-14, h * 1e-13) and not self.impact:
            # Rare pathological repeated-contact fallback: retain responsiveness
            # and finish with small conservative substeps rather than loop forever.
            chunk = remaining / 32.0
            for _ in range(32):
                self._integrate_interval(chunk, method)
                self.t += chunk
                if self.collision != PASS:
                    self._handle_collisions()
                    if self.impact:
                        break

    def _integrate_interval(self, h: float, method: str):
        if h <= 0.0:
            return
        if method == VERLET:
            self._verlet(h)
        elif method == YOSHIDA:
            self._yoshida(h)
        elif method == RK45:
            self._rk45_integrate(h)
        else:
            raise ValueError(f"Unknown integrator: {method}")

    def _derivative(self, state: np.ndarray) -> np.ndarray:
        p = state[:9].reshape(3, 3)
        v = state[9:18].reshape(3, 3)
        a = self.accelerations(p, v)
        derivative = np.concatenate((v.ravel(), a.ravel()))
        if state.size > 18:
            # Integrate cumulative tidal heat as an auxiliary ODE state, so the
            # energy budget uses the same adaptive stages as the orbit.
            return np.concatenate((derivative, [self._tidal_dissipation_power(p, v)]))
        return derivative

    def _rk45_trial(self, state: np.ndarray, h: float):
        """One Dormand–Prince 5(4) trial; returns fifth-order state and error."""
        f = self._derivative
        k1 = f(state)
        k2 = f(state + h * (1/5) * k1)
        k3 = f(state + h * ((3/40) * k1 + (9/40) * k2))
        k4 = f(state + h * ((44/45) * k1 - (56/15) * k2 + (32/9) * k3))
        k5 = f(state + h * ((19372/6561) * k1 - (25360/2187) * k2
                            + (64448/6561) * k3 - (212/729) * k4))
        k6 = f(state + h * ((9017/3168) * k1 - (355/33) * k2
                            + (46732/5247) * k3 + (49/176) * k4
                            - (5103/18656) * k5))
        y5 = state + h * ((35/384) * k1 + (500/1113) * k3 + (125/192) * k4
                          - (2187/6784) * k5 + (11/84) * k6)
        k7 = f(y5)
        y4 = state + h * ((5179/57600) * k1 + (7571/16695) * k3 + (393/640) * k4
                          - (92097/339200) * k5 + (187/2100) * k6 + (1/40) * k7)
        return y5, y5 - y4

    def _tidal_dissipation_power(self, pos=None, vel=None) -> float:
        if self.tidal_damping <= 0.0:
            return 0.0
        p = self.pos if pos is None else pos
        v = self.vel if vel is None else vel
        power = 0.0
        for i, j in PAIRS:
            if not (self.alive[i] and self.alive[j]):
                continue
            r = p[i] - p[j]
            dist = float(np.linalg.norm(r))
            if dist <= 1e-15:
                continue
            vr = float(((v[i] - v[j]) @ (r / dist)))
            mu = self.m[i] * self.m[j] / (self.m[i] + self.m[j])
            power += mu * self.tidal_damping * vr * vr
        return power

    def _rk45_integrate(self, interval: float):
        """Integrate an interval with local error-controlled Dormand–Prince RK45."""
        if self.tidal_damping > 0.0:
            state = np.concatenate((self.pos.ravel(), self.vel.ravel(), [0.0])).astype(float)
        else:
            state = np.concatenate((self.pos.ravel(), self.vel.ravel())).astype(float)
        elapsed = 0.0
        h_next = interval
        accepted = rejected = 0
        max_trials = 20000
        trials = 0
        while elapsed < interval - max(1e-14, interval * 1e-13):
            trials += 1
            if trials > max_trials:
                raise RuntimeError("RK45 exceeded its step budget; increase tolerances or reduce the time interval.")
            h = min(h_next, interval - elapsed)
            y5, error = self._rk45_trial(state, h)
            scale = self.atol + self.rtol * np.maximum(np.abs(state), np.abs(y5))
            err_norm = float(np.sqrt(np.mean((error / scale) ** 2)))
            self.rk45_last_error = err_norm
            if math.isfinite(err_norm) and err_norm <= 1.0:
                state = y5
                elapsed += h
                accepted += 1
                factor = 5.0 if err_norm == 0.0 else min(5.0, max(0.2, 0.9 * err_norm ** (-0.2)))
                h_next = h * factor
            else:
                rejected += 1
                factor = 0.1 if not math.isfinite(err_norm) else max(0.1, min(0.5, 0.9 * err_norm ** (-0.2)))
                h_next = h * factor
                if h_next <= np.finfo(float).eps * max(1.0, abs(elapsed)):
                    raise RuntimeError("RK45 step underflow; dynamics may be singular or tolerances too strict.")
        self.pos = state[:9].reshape(3, 3).copy()
        self.vel = state[9:18].reshape(3, 3).copy()
        if self.tidal_damping > 0.0:
            self.tidal_energy_dissipated += max(0.0, float(state[18]))
        self._acc = None
        self.rk45_accepted_steps += accepted
        self.rk45_rejected_steps += rejected

    def _earliest_contact_time(self):
        """Estimate first sphere contact from current relative position/velocity."""
        earliest = math.inf
        pair_best = None
        for i, j in PAIRS:
            if not (self.alive[i] and self.alive[j]):
                continue
            r = self.pos[j] - self.pos[i]
            v = self.vel[j] - self.vel[i]
            radius = self.R[i] + self.R[j]
            c = float(r @ r) - radius * radius
            radial = float(r @ v)
            tol = 1e-12 * max(1.0, radius * radius)
            if c <= tol:
                if radial < 0.0 or c < -tol:
                    return (i, j), 0.0
                continue
            a = float(v @ v)
            if a <= 1e-30 or radial >= 0.0:
                continue
            b = 2.0 * radial
            disc = b * b - 4.0 * a * c
            if disc < 0.0:
                continue
            root = (-b - math.sqrt(max(0.0, disc))) / (2.0 * a)
            if root >= 0.0 and root < earliest:
                earliest, pair_best = root, (i, j)
        return pair_best, earliest

    def _swept_first_contact(self, start_pos: np.ndarray, end_pos: np.ndarray,
                             start_alive: np.ndarray):
        """Detect sphere contact even when the end points have passed through."""
        earliest = math.inf
        pair_best = None
        for i, j in PAIRS:
            if not (start_alive[i] and start_alive[j] and self.alive[i] and self.alive[j]):
                continue
            r0 = start_pos[j] - start_pos[i]
            rend = end_pos[j] - end_pos[i]
            dr = rend - r0
            radius = self.R[i] + self.R[j]
            c = float(r0 @ r0) - radius * radius
            radial = float(r0 @ dr)
            if c <= 1e-12 * max(1.0, radius * radius):
                if radial < 0.0:
                    return (i, j), 0.0
                continue
            a = float(dr @ dr)
            if a <= 1e-30 or radial >= 0.0:
                continue
            disc = radial * radial - a * c
            if disc < 0.0:
                continue
            fraction = (-radial - math.sqrt(max(0.0, disc))) / a
            if 0.0 <= fraction <= 1.0 and fraction < earliest:
                earliest, pair_best = fraction, (i, j)
        return (pair_best, earliest) if pair_best is not None else None

    def _snap_to_contact(self, i: int, j: int):
        """Correct tiny event-location error while preserving the pair COM."""
        delta = self.pos[j] - self.pos[i]
        distance = float(np.linalg.norm(delta))
        if distance > 1e-15:
            normal = delta / distance
        else:
            relv = self.vel[j] - self.vel[i]
            speed = float(np.linalg.norm(relv))
            normal = relv / speed if speed > 1e-15 else np.array([1.0, 0.0, 0.0])
        mi, mj = self.m[i], self.m[j]
        total = mi + mj
        com = (mi * self.pos[i] + mj * self.pos[j]) / total
        target = self.R[i] + self.R[j]
        self.pos[i] = com - normal * target * mj / total
        self.pos[j] = com + normal * target * mi / total

    def _resolve_collision_pair(self, i: int, j: int):
        if not (self.alive[i] and self.alive[j]):
            return
        if self.collision == STOP:
            if (i, j) not in self._touching:
                self._touching.add((i, j))
                self.impact = True
                self.events.append((self.t, f"Impact: Body {i + 1} and Body {j + 1}"))
            return
        before = self.energy()
        if self.collision == MERGE:
            self._merge(i, j)
        elif self.collision == FRAGMENT:
            self._fragment(i, j)
        elif self.collision == BOUNCE:
            delta = self.pos[j] - self.pos[i]
            distance = float(np.linalg.norm(delta))
            self._bounce(i, j, delta, distance)
        after = self.energy()
        self.energy_lost += before - after
        self._acc = None

    def _verlet(self, h: float):
        if self._acc is None:
            self._acc = self.accelerations(self.pos)
        a0 = self._acc
        self.pos = self.pos + self.vel * h + 0.5 * a0 * h * h
        a1 = self.accelerations(self.pos)
        self.vel = self.vel + 0.5 * (a0 + a1) * h
        self._acc = a1

    def _yoshida(self, h: float):
        p, v = self.pos.copy(), self.vel.copy()
        for k in range(3):
            p = p + self._C[k] * h * v
            v = v + self._D[k] * h * self.accelerations(p)
        self.pos, self.vel = p + self._C[3] * h * v, v
        self._acc = None

    def advance(self, steps: float, dt: float, method: str = YOSHIDA,
                adaptive: bool = False, eta: float = 0.02, max_wall: float = 0.012) -> int:
        """Advance by roughly steps*dt while bounding per-frame wall-clock work."""
        if dt <= 0 or steps <= 0:
            return 0
        if method not in INTEGRATORS:
            raise ValueError(f"Unknown integrator: {method}")
        start = time.perf_counter()
        taken = 0
        if adaptive:
            target = self.t + float(steps) * dt
            while self.t < target - 1e-13:
                tau = self.timescale()
                h = min(dt, eta * tau if math.isfinite(tau) else dt, target - self.t)
                h = max(h, dt * 1e-7)
                self.step(h, method)
                taken += 1
                if self.impact or (taken % 8 == 0 and time.perf_counter() - start > max_wall):
                    break
        else:
            for _ in range(max(1, int(round(steps)))):
                self.step(dt, method)
                taken += 1
                if self.impact or (taken % 8 == 0 and time.perf_counter() - start > max_wall):
                    break
        return taken

    def _handle_collisions(self):
        for i, j in PAIRS:
            if not (self.alive[i] and self.alive[j]):
                self._touching.discard((i, j))
                continue
            distance = float(np.linalg.norm(self.pos[j] - self.pos[i]))
            radius_sum = self.R[i] + self.R[j]
            if distance < radius_sum:
                self._resolve_collision_pair(i, j)

    def _merge(self, i: int, j: int):
        survivor, removed = (i, j) if self.m[i] >= self.m[j] else (j, i)
        mi, mj = self.m[i], self.m[j]
        total = mi + mj
        ri, rj = self.pos[i].copy(), self.pos[j].copy()
        vi, vj = self.vel[i].copy(), self.vel[j].copy()
        new_pos = (mi * ri + mj * rj) / total
        new_vel = (mi * vi + mj * vj) / total
        reduced = mi * mj / total
        internal_L = reduced * np.cross(rj - ri, vj - vi)
        new_spin = self.spin[i] + self.spin[j] + internal_L
        new_radius = (self.R[i]**3 + self.R[j]**3) ** (1.0 / 3.0)
        self.m[survivor] = total
        self.pos[survivor] = new_pos
        self.vel[survivor] = new_vel
        self.R[survivor] = new_radius
        self.spin[survivor] = new_spin
        new_inertia = 0.4 * total * new_radius**2
        self.spin_omega[survivor] = new_spin / new_inertia if new_inertia > 0 else 0.0
        # Preserve a mass-weighted effective J2 for the merged remnant; the merged
        # body's real shape/spin must be recalibrated for research-grade work.
        self.j2[survivor] = (self.j2[i] * mi + self.j2[j] * mj) / total
        if np.linalg.norm(self.spin[survivor]) > 1e-15:
            self.spin_axes[survivor] = self.spin[survivor] / np.linalg.norm(self.spin[survivor])
        self.alive[removed] = False
        self.m[removed] = 0.0
        self.R[removed] = 0.0
        self.pos[removed] = new_pos
        self.vel[removed] = 0.0
        self.spin[removed] = 0.0
        self.spin_omega[removed] = 0.0
        self.j2[removed] = 0.0
        self._refresh_mask()
        self.events.append((self.t, f"Body {removed + 1} merged into Body {survivor + 1}; new mass={total:.5g}, radius={new_radius:.5g}"))

    def _fragment(self, i: int, j: int):
        """Toy collision-fragmentation model retaining two resolved remnants.

        It conserves pair mass and linear momentum, partitions volume, and reduces
        relative translational kinetic energy. It is a visual/educational surrogate,
        not a material-strength or hydrodynamic impact model.
        """
        mi0, mj0 = float(self.m[i]), float(self.m[j])
        total = mi0 + mj0
        if total <= 0:
            return
        old_pos_i, old_pos_j = self.pos[i].copy(), self.pos[j].copy()
        old_vel_i, old_vel_j = self.vel[i].copy(), self.vel[j].copy()
        delta = old_pos_j - old_pos_i
        distance = float(np.linalg.norm(delta))
        normal = delta / distance if distance > 1e-15 else np.array([1.0, 0.0, 0.0])
        com = (mi0 * old_pos_i + mj0 * old_pos_j) / total
        vcom = (mi0 * old_vel_i + mj0 * old_vel_j) / total
        rel_speed = float(np.linalg.norm(old_vel_j - old_vel_i))
        # The smaller remnant receives 30% of total mass; the remaining mass stays
        # with the primary remnant. Volume-equivalent radii conserve total volume.
        m_primary, m_fragment = 0.7 * total, 0.3 * total
        volume = self.R[i]**3 + self.R[j]**3
        r_primary = (0.7 * volume)**(1.0/3.0)
        r_fragment = (0.3 * volume)**(1.0/3.0)
        # Put both remnants at contact and send them gently apart along the contact
        # normal. The relative kick is limited to a fraction of pre-impact speed.
        separation = r_primary + r_fragment
        self.m[i], self.m[j] = m_primary, m_fragment
        self.R[i], self.R[j] = r_primary, r_fragment
        reduced_mass = mi0 * mj0 / total
        # The toy remnants separate along the contact normal, so their new
        # relative orbital angular momentum is zero. Transfer the pre-impact
        # pair orbital angular momentum into the remnant spins to preserve the
        # pair's total angular momentum around its center of mass.
        impact_orbital_L = reduced_mass * np.cross(old_pos_j - old_pos_i, old_vel_j - old_vel_i)
        total_spin = self.spin[i].copy() + self.spin[j].copy() + impact_orbital_L
        self.spin[i], self.spin[j] = 0.7 * total_spin, 0.3 * total_spin
        Ii, Ij = 0.4 * m_primary * r_primary**2, 0.4 * m_fragment * r_fragment**2
        self.spin_omega[i] = self.spin[i] / max(Ii, 1e-30)
        self.spin_omega[j] = self.spin[j] / max(Ij, 1e-30)
        self.pos[i] = com - normal * separation * m_fragment / total
        self.pos[j] = com + normal * separation * m_primary / total
        kick = max(0.25 * rel_speed, 1e-8)
        self.vel[i] = vcom - normal * kick * m_fragment / total
        self.vel[j] = vcom + normal * kick * m_primary / total
        self._refresh_mask()
        self.events.append((self.t, f"Bodies {i+1}/{j+1} fragmented into two remnants (70/30 mass split; toy model)"))

    def _bounce(self, i: int, j: int, delta: np.ndarray, distance: float):
        n = delta / distance if distance > 1e-15 else np.array([1.0, 0.0, 0.0])
        vrel = float((self.vel[i] - self.vel[j]) @ n)
        if vrel > 0:
            impulse = (1.0 + self.restitution) * vrel / (1.0 / self.m[i] + 1.0 / self.m[j])
            self.vel[i] -= impulse / self.m[i] * n
            self.vel[j] += impulse / self.m[j] * n
            self.events.append((self.t, f"Bodies {i + 1} and {j + 1} bounced; normal approach speed={vrel:.5g}"))
        overlap = max(0.0, self.R[i] + self.R[j] - distance)
        correction = overlap / (self.m[i] + self.m[j])
        self.pos[i] -= correction * self.m[j] * n
        self.pos[j] += correction * self.m[i] * n

    def recenter(self):
        """Move to the center-of-mass frame without changing relative trajectories."""
        self.pos -= self.center_of_mass()
        self.vel -= self.center_velocity()
        self._acc = None


class History:
    """Small rolling diagnostic history used by the GUI graphs and CSV export."""
    def __init__(self, maxlen: int = 2500):
        self.t = deque(maxlen=maxlen)
        self.separations = [deque(maxlen=maxlen) for _ in PAIRS]
        self.energy_error = deque(maxlen=maxlen)
        self.momentum_error = deque(maxlen=maxlen)
        self.angular_momentum_error = deque(maxlen=maxlen)
        self.positions = deque(maxlen=maxlen)
        self.velocities = deque(maxlen=maxlen)

    def push(self, engine: ThreeBodyEngine):
        self.t.append(engine.t)
        for series, d in zip(self.separations, engine.pair_distances()):
            series.append(float(d))
        energy_error = float(engine.energy_error())
        momentum_error = float(engine.momentum_error())
        angular_error = float(engine.angular_momentum_error())
        self.energy_error.append(energy_error if math.isfinite(energy_error) else math.nan)
        self.momentum_error.append(momentum_error if math.isfinite(momentum_error) else math.nan)
        self.angular_momentum_error.append(angular_error if math.isfinite(angular_error) else math.nan)
        self.positions.append(tuple(tuple(float(x) for x in row) for row in engine.pos))
        self.velocities.append(tuple(tuple(float(x) for x in row) for row in engine.vel))
