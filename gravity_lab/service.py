"""GUI-independent application service around the three-body physics engine.

The service is the transitional boundary between validated application state
and the mutable numerical engine. It contains no Tkinter or VTK imports.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Iterable

import numpy as np

from .physics import ThreeBodyEngine, RK45, YOSHIDA
from .state import BodyState, IntegratorSettings, PhysicsSettings, SimulationState


Vector3 = tuple[float, float, float]
Matrix3 = tuple[Vector3, Vector3, Vector3]


def _vector(values: Iterable[float]) -> Vector3:
    array = np.asarray(tuple(values), dtype=float).reshape(3)
    return tuple(float(value) for value in array)  # type: ignore[return-value]


def _matrix(values: object) -> Matrix3:
    array = np.asarray(values, dtype=float).reshape(3, 3)
    return tuple(_vector(row) for row in array)  # type: ignore[return-value]


def _finite_or_none(value: object) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _minimum_active_separation(positions: np.ndarray, active: np.ndarray) -> float | None:
    distances: list[float] = []
    for i in range(3):
        if not active[i] or not np.all(np.isfinite(positions[i])):
            continue
        for j in range(i + 1, 3):
            if not active[j] or not np.all(np.isfinite(positions[j])):
                continue
            distance = float(np.linalg.norm(positions[j] - positions[i]))
            if math.isfinite(distance):
                distances.append(distance)
    return min(distances) if distances else None


@dataclass(frozen=True, slots=True)
class SimulationSnapshot:
    """Immutable read-only view of the mutable engine at one simulation time."""

    time: float
    positions: Matrix3
    velocities: Matrix3
    masses: Vector3
    radii: Vector3
    active: tuple[bool, bool, bool]
    energy: float | None
    energy_error: float | None
    momentum: Vector3
    momentum_error: float | None
    angular_momentum: Vector3
    angular_momentum_error: float | None
    minimum_separation: float | None
    events: tuple[tuple[float, str], ...]
    impact: bool
    healthy: bool
    rk45_last_error: float | None
    rk45_accepted_steps: int
    rk45_rejected_steps: int

    @classmethod
    def from_engine(cls, engine: ThreeBodyEngine) -> "SimulationSnapshot":
        positions = np.asarray(engine.pos, dtype=float).reshape(3, 3).copy()
        velocities = np.asarray(engine.vel, dtype=float).reshape(3, 3).copy()
        active = np.asarray(engine.alive, dtype=bool).reshape(3).copy()
        momentum = np.asarray(engine.linear_momentum(), dtype=float).reshape(3)
        angular = np.asarray(engine.angular_momentum(), dtype=float).reshape(3)
        return cls(
            time=float(engine.t),
            positions=_matrix(positions),
            velocities=_matrix(velocities),
            masses=_vector(engine.m),
            radii=_vector(engine.R),
            active=tuple(bool(value) for value in active),  # type: ignore[arg-type]
            energy=_finite_or_none(engine.energy()),
            energy_error=_finite_or_none(engine.energy_error()),
            momentum=_vector(momentum),
            momentum_error=_finite_or_none(engine.momentum_error()),
            angular_momentum=_vector(angular),
            angular_momentum_error=_finite_or_none(engine.angular_momentum_error()),
            minimum_separation=_minimum_active_separation(positions, active),
            events=tuple((float(t), str(event)) for t, event in engine.events),
            impact=bool(engine.impact),
            healthy=bool(engine.is_healthy()),
            rk45_last_error=_finite_or_none(engine.rk45_last_error),
            rk45_accepted_steps=int(engine.rk45_accepted_steps),
            rk45_rejected_steps=int(engine.rk45_rejected_steps),
        )


def engine_from_state(state: SimulationState) -> ThreeBodyEngine:
    """Materialize a physics engine from a validated state without UI objects."""
    if not isinstance(state, SimulationState):
        raise TypeError("state must be a SimulationState instance")

    masses = [body.mass for body in state.bodies]
    radii = [body.radius for body in state.bodies]
    positions = np.asarray([body.position for body in state.bodies], dtype=float)
    velocities = np.asarray([body.velocity for body in state.bodies], dtype=float)
    active = np.asarray([body.active for body in state.bodies], dtype=bool)
    physics = state.physics

    # The legacy engine constructor checks coincidences before it knows about
    # inactive bodies. Use temporary positions only for construction where an
    # inactive record shares a position, then restore the exact supplied state
    # before taking any baseline diagnostics or stepping.
    constructor_positions = positions.copy()
    if physics.softening == 0.0:
        scale = max(1.0, float(np.max(np.abs(positions)))) * 1e-6
        for i in range(3):
            if active[i]:
                continue
            offset = 1
            while any(np.array_equal(constructor_positions[i], constructor_positions[j]) for j in range(3) if j != i):
                constructor_positions[i] = positions[i] + np.array([scale * offset, scale * (offset + 1), scale * (offset + 2)])
                offset += 1
                if offset > 1000:
                    raise ValueError("Could not prepare a unique temporary constructor position for an inactive body.")

    engine = ThreeBodyEngine(
        masses=masses,
        radii=radii,
        positions=constructor_positions,
        velocities=velocities,
        G=physics.gravitational_constant,
        softening=physics.softening,
        collision=physics.collision_mode,
        restitution=physics.restitution,
        rtol=state.integrator.rtol,
        atol=state.integrator.atol,
        enable_oblateness=physics.enable_oblateness,
        j2=[body.j2 for body in state.bodies],
        spin_axes=[body.spin_axis for body in state.bodies],
        spin_omega=[body.spin_omega for body in state.bodies],
        enable_1pn=physics.enable_1pn,
        c_light=physics.c_light,
        tidal_damping=physics.tidal_damping,
    )

    # Install the exact state and establish diagnostics against this initial
    # condition (also handles inactive-body positions and a non-zero t value).
    engine.pos = positions.copy()
    engine.vel = velocities.copy()
    engine.alive = active.copy()
    engine._refresh_mask()
    engine._acc = None
    engine.t = float(state.current_time)
    engine.events.clear()
    engine.impact = False
    engine._touching.clear()
    engine.energy_lost = 0.0
    engine.tidal_energy_dissipated = 0.0
    engine.e0 = engine.energy()
    engine.p0 = engine.linear_momentum().copy()
    engine.l0 = engine.angular_momentum().copy()
    return engine


class SimulationService:
    """Own simulation state transitions and expose explicit snapshots.

    ``engine`` is exposed temporarily for compatibility with the existing VTK
    renderer and history collector. New application code should prefer
    ``snapshot()``, ``advance()``, and ``state`` rather than mutating arrays.
    """

    def __init__(self, initial_state: SimulationState | None = None):
        self.state: SimulationState | None = None
        self._engine: ThreeBodyEngine | None = None
        if initial_state is not None:
            self.reset(initial_state)

    @property
    def engine(self) -> ThreeBodyEngine | None:
        """Compatibility access to the live engine for existing renderer code."""
        return self._engine

    def reset(self, state: SimulationState) -> SimulationSnapshot:
        """Replace the current simulation with a new validated initial state."""
        engine = engine_from_state(state)
        self._engine = engine
        self.state = state
        self._sync_state_from_engine()
        return self.snapshot()

    def snapshot(self) -> SimulationSnapshot:
        if self._engine is None:
            raise RuntimeError("No simulation has been configured. Call reset(state) first.")
        return SimulationSnapshot.from_engine(self._engine)

    def advance(
        self,
        steps: float | None = None,
        dt: float | None = None,
        method: str | None = None,
        *,
        adaptive: bool | None = None,
        max_wall: float = 0.012,
    ) -> SimulationSnapshot:
        """Advance one frame and return an immutable diagnostics snapshot.

        The default budget comes from the current ``SimulationState``. Optional
        overrides support the existing UI speed slider during the migration.
        """
        if self._engine is None or self.state is None:
            raise RuntimeError("No simulation has been configured. Call reset(state) first.")
        settings = self.state.integrator
        chosen_steps = settings.steps_per_frame if steps is None else float(steps)
        chosen_dt = settings.dt if dt is None else float(dt)
        chosen_method = settings.method if method is None else method
        chosen_adaptive = settings.adaptive if adaptive is None else bool(adaptive)
        if not math.isfinite(chosen_steps) or chosen_steps <= 0:
            raise ValueError("Frame step count must be finite and positive.")
        if not math.isfinite(chosen_dt) or chosen_dt <= 0:
            raise ValueError("Frame time step must be finite and positive.")
        if not math.isfinite(max_wall) or max_wall <= 0:
            raise ValueError("Frame wall-time budget must be finite and positive.")
        self._engine.advance(chosen_steps, chosen_dt, chosen_method,
                             adaptive=chosen_adaptive, max_wall=max_wall)

        # Keep the explicit model aligned with the engine's latest healthy state.
        if self._engine.is_healthy():
            self._sync_state_from_engine(
                integrator=IntegratorSettings(
                    method=chosen_method,
                    # `dt` can be scaled for the current GUI frame (speed slider);
                    # keep the configured/base step in explicit application state.
                    dt=settings.dt,
                    steps_per_frame=max(1, min(1000, int(round(chosen_steps)))),
                    adaptive=chosen_adaptive,
                    rtol=settings.rtol,
                    atol=settings.atol,
                )
            )
        return self.snapshot()

    def step(self, h: float | None = None, method: str | None = None) -> SimulationSnapshot:
        """Advance by one explicit model-time interval."""
        if self._engine is None or self.state is None:
            raise RuntimeError("No simulation has been configured. Call reset(state) first.")
        chosen_h = self.state.integrator.dt if h is None else float(h)
        chosen_method = self.state.integrator.method if method is None else method
        self._engine.step(chosen_h, chosen_method)
        if self._engine.is_healthy():
            self._sync_state_from_engine()
        return self.snapshot()

    def _sync_state_from_engine(self, integrator: IntegratorSettings | None = None) -> None:
        assert self._engine is not None and self.state is not None
        engine = self._engine
        prior = self.state
        if not engine.is_healthy():
            return
        bodies = []
        for i, old in enumerate(prior.bodies):
            # Inactive merge slots can have zero engine mass/radius; retain their
            # positive body record while marking active=False in application state.
            mass = float(engine.m[i]) if engine.m[i] > 0.0 else old.mass
            radius = float(engine.R[i]) if engine.R[i] > 0.0 else old.radius
            bodies.append(BodyState(
                name=old.name,
                mass=mass,
                radius=radius,
                position=_vector(engine.pos[i]),
                velocity=_vector(engine.vel[i]),
                active=bool(engine.alive[i]),
                color=old.color,
                j2=float(engine.j2[i]),
                spin_axis=_vector(engine.spin_axes[i]),
                spin_omega=_vector(engine.spin_omega[i]),
            ))
        old_physics = prior.physics
        physics = PhysicsSettings(
            gravitational_constant=float(engine.G),
            softening=float(engine.softening),
            collision_mode=engine.collision,
            restitution=float(engine.restitution),
            units=old_physics.units,
            enable_oblateness=bool(engine.enable_oblateness),
            enable_1pn=bool(engine.enable_1pn),
            c_light=float(engine.c_light),
            tidal_damping=float(engine.tidal_damping),
        )
        try:
            self.state = SimulationState(
                bodies=tuple(bodies),  # type: ignore[arg-type]
                current_time=float(engine.t),
                integrator=integrator or prior.integrator,
                physics=physics,
            )
        except ValueError:
            # A failed/inconsistent engine state should not overwrite the last
            # validated application state. The diagnostics snapshot still shows
            # current values and health separately.
            return
