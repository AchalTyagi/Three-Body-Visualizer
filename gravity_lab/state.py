"""Explicit, validated data model for a Gravity Lab three-body simulation.

The state model is deliberately independent of Tkinter and VTK.  It describes
physical body state, presentation metadata, model settings, and integrator
settings without owning a window or a running engine instance.

Persistent setup-file versioning remains the responsibility of the setup I/O
layer; ``to_mapping``/``from_mapping`` are structural conversions intended for
application boundaries and tests, not a promise of a stable on-disk schema.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import re
from typing import Any, Mapping, Sequence

from .physics import COLLISION_MODES, INTEGRATORS, MERGE, YOSHIDA

_VECTOR_LENGTH = 3
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def _finite_number(value: Any, label: str) -> float:
    """Return ``value`` as a finite float or raise an actionable ValueError."""
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a finite number, not a boolean.")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{label} must be a finite number.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite.")
    return number


def _vector3(value: Sequence[Any], label: str) -> tuple[float, float, float]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or len(value) != _VECTOR_LENGTH:
        raise ValueError(f"{label} must contain exactly three numeric components.")
    return tuple(_finite_number(component, f"{label}[{index}]")
                 for index, component in enumerate(value))  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class BodyState:
    """One body's physical state plus stable display metadata.

    ``active`` corresponds to the engine's per-body ``alive`` flag. The engine
    remains the authority during an integration step; this value is the
    explicit application-level representation.
    """

    name: str
    mass: float
    radius: float
    position: tuple[float, float, float]
    velocity: tuple[float, float, float]
    active: bool = True
    color: str = "#40c4ff"
    j2: float = 0.0
    spin_axis: tuple[float, float, float] = (0.0, 0.0, 1.0)
    spin_omega: tuple[float, float, float] = (0.0, 0.0, 0.0)

    def __post_init__(self) -> None:
        name = str(self.name).strip()
        if not name:
            raise ValueError("Body name cannot be empty.")
        object.__setattr__(self, "name", name)

        mass = _finite_number(self.mass, f"{name} mass")
        radius = _finite_number(self.radius, f"{name} radius")
        if mass <= 0.0:
            raise ValueError(f"{name} mass must be greater than zero.")
        if radius <= 0.0:
            raise ValueError(f"{name} radius must be greater than zero.")
        object.__setattr__(self, "mass", mass)
        object.__setattr__(self, "radius", radius)
        object.__setattr__(self, "position", _vector3(self.position, f"{name} position"))
        object.__setattr__(self, "velocity", _vector3(self.velocity, f"{name} velocity"))
        object.__setattr__(self, "spin_axis", _vector3(self.spin_axis, f"{name} spin axis"))
        object.__setattr__(self, "spin_omega", _vector3(self.spin_omega, f"{name} spin angular velocity"))
        j2 = _finite_number(self.j2, f"{name} J2")
        object.__setattr__(self, "j2", j2)
        if not isinstance(self.active, bool):
            raise ValueError(f"{name} active flag must be a boolean.")
        if not isinstance(self.color, str) or not _HEX_COLOR.fullmatch(self.color):
            raise ValueError(f"{name} colour must be a six-digit hex colour such as #40c4ff.")


@dataclass(frozen=True, slots=True)
class IntegratorSettings:
    """Numerical integration choices separated from the GUI controls."""

    method: str = YOSHIDA
    dt: float = 0.003
    steps_per_frame: int = 4
    adaptive: bool = True
    rtol: float = 1e-9
    atol: float = 1e-12

    def __post_init__(self) -> None:
        if self.method not in INTEGRATORS:
            raise ValueError(f"Unknown integration method: {self.method!r}.")
        dt = _finite_number(self.dt, "Time step Δt")
        rtol = _finite_number(self.rtol, "RK45 relative tolerance")
        atol = _finite_number(self.atol, "RK45 absolute tolerance")
        if dt <= 0.0:
            raise ValueError("Time step Δt must be greater than zero.")
        if isinstance(self.steps_per_frame, bool) or not isinstance(self.steps_per_frame, int):
            raise ValueError("Steps per frame must be an integer.")
        if not 1 <= self.steps_per_frame <= 1000:
            raise ValueError("Steps per frame must be between 1 and 1000.")
        if not isinstance(self.adaptive, bool):
            raise ValueError("Adaptive stepping must be a boolean.")
        if not 0.0 < rtol < 1.0:
            raise ValueError("RK45 relative tolerance must satisfy 0 < rtol < 1.")
        if atol <= 0.0:
            raise ValueError("RK45 absolute tolerance must be greater than zero.")
        object.__setattr__(self, "dt", dt)
        object.__setattr__(self, "rtol", rtol)
        object.__setattr__(self, "atol", atol)


@dataclass(frozen=True, slots=True)
class PhysicsSettings:
    """Physical model options, independent of widget variables."""

    gravitational_constant: float = 1.0
    softening: float = 0.0
    collision_mode: str = MERGE
    restitution: float = 1.0
    units: str = "Arbitrary units"
    enable_oblateness: bool = False
    enable_1pn: bool = False
    c_light: float = 1000.0
    tidal_damping: float = 0.0

    def __post_init__(self) -> None:
        g = _finite_number(self.gravitational_constant, "Gravitational constant G")
        softening = _finite_number(self.softening, "Softening ε")
        restitution = _finite_number(self.restitution, "Bounce restitution")
        c_light = _finite_number(self.c_light, "Speed of light in model units")
        tidal_damping = _finite_number(self.tidal_damping, "Tidal damping coefficient")
        if g < 0.0:
            raise ValueError("Gravitational constant G must be non-negative.")
        if softening < 0.0:
            raise ValueError("Softening ε must be non-negative.")
        if self.collision_mode not in COLLISION_MODES:
            raise ValueError(f"Unknown collision mode: {self.collision_mode!r}.")
        if not 0.0 <= restitution <= 1.0:
            raise ValueError("Bounce restitution must be between 0 and 1.")
        if not isinstance(self.units, str) or not self.units.strip():
            raise ValueError("Units label cannot be empty.")
        if not isinstance(self.enable_oblateness, bool) or not isinstance(self.enable_1pn, bool):
            raise ValueError("Advanced-physics enable flags must be booleans.")
        if c_light <= 0.0:
            raise ValueError("Speed of light in model units must be greater than zero.")
        if tidal_damping < 0.0:
            raise ValueError("Tidal damping coefficient must be non-negative.")
        if (self.enable_oblateness or self.enable_1pn) and softening != 0.0:
            raise ValueError("J2 and 1PN corrections require zero softening.")
        object.__setattr__(self, "gravitational_constant", g)
        object.__setattr__(self, "softening", softening)
        object.__setattr__(self, "restitution", restitution)
        object.__setattr__(self, "c_light", c_light)
        object.__setattr__(self, "tidal_damping", tidal_damping)


@dataclass(frozen=True, slots=True)
class SimulationState:
    """Validated snapshot of a complete three-body model at a given time.

    This is intentionally a data model, not a second integrator. Runtime
    evolution stays in :class:`gravity_lab.physics.ThreeBodyEngine`; the model
    supplies a single, testable boundary for values passed to/from app layers.
    """

    bodies: tuple[BodyState, BodyState, BodyState]
    current_time: float = 0.0
    integrator: IntegratorSettings = field(default_factory=IntegratorSettings)
    physics: PhysicsSettings = field(default_factory=PhysicsSettings)

    def __post_init__(self) -> None:
        bodies = tuple(self.bodies)
        if len(bodies) != 3:
            raise ValueError(f"Gravity Lab currently requires exactly three bodies; received {len(bodies)}.")
        if not all(isinstance(body, BodyState) for body in bodies):
            raise ValueError("Every item in bodies must be a BodyState.")
        object.__setattr__(self, "bodies", bodies)
        current_time = _finite_number(self.current_time, "Simulation time")
        object.__setattr__(self, "current_time", current_time)
        if not isinstance(self.integrator, IntegratorSettings):
            raise ValueError("integrator must be an IntegratorSettings instance.")
        if not isinstance(self.physics, PhysicsSettings):
            raise ValueError("physics must be a PhysicsSettings instance.")
        if (self.physics.enable_1pn or self.physics.tidal_damping > 0.0) and self.integrator.method != "Dormand–Prince RK45 (adaptive)":
            raise ValueError("The 1PN and tidal-damping models require Dormand–Prince RK45.")
        if self.physics.softening == 0.0:
            active = [(i, body) for i, body in enumerate(bodies) if body.active]
            for index, (i, body_i) in enumerate(active):
                for j, body_j in active[index + 1:]:
                    if body_i.position == body_j.position:
                        raise ValueError(
                            f"Active bodies {i + 1} and {j + 1} cannot occupy the exact same position when softening is zero."
                        )

    def to_mapping(self) -> dict[str, Any]:
        """Convert to plain Python mappings/lists for boundaries and tests.

        This mapping has no disk-schema compatibility guarantee; versioned setup
        and checkpoint formats are handled by their dedicated future I/O layer.
        """
        return {
            "bodies": [
                {
                    "name": body.name,
                    "mass": body.mass,
                    "radius": body.radius,
                    "position": list(body.position),
                    "velocity": list(body.velocity),
                    "active": body.active,
                    "color": body.color,
                    "j2": body.j2,
                    "spin_axis": list(body.spin_axis),
                    "spin_omega": list(body.spin_omega),
                }
                for body in self.bodies
            ],
            "current_time": self.current_time,
            "integrator": {
                "method": self.integrator.method,
                "dt": self.integrator.dt,
                "steps_per_frame": self.integrator.steps_per_frame,
                "adaptive": self.integrator.adaptive,
                "rtol": self.integrator.rtol,
                "atol": self.integrator.atol,
            },
            "physics": {
                "gravitational_constant": self.physics.gravitational_constant,
                "softening": self.physics.softening,
                "collision_mode": self.physics.collision_mode,
                "restitution": self.physics.restitution,
                "units": self.physics.units,
                "enable_oblateness": self.physics.enable_oblateness,
                "enable_1pn": self.physics.enable_1pn,
                "c_light": self.physics.c_light,
                "tidal_damping": self.physics.tidal_damping,
            },
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "SimulationState":
        """Build a validated state from a plain mapping."""
        if not isinstance(payload, Mapping):
            raise ValueError("Simulation state must be a mapping.")
        try:
            raw_bodies = payload["bodies"]
            raw_integrator = payload.get("integrator", {})
            raw_physics = payload.get("physics", {})
            if not isinstance(raw_bodies, Sequence) or isinstance(raw_bodies, (str, bytes)):
                raise ValueError("bodies must be a sequence of three body mappings.")
            if not isinstance(raw_integrator, Mapping) or not isinstance(raw_physics, Mapping):
                raise ValueError("integrator and physics must be mappings.")
            bodies = tuple(
                BodyState(
                    name=item["name"],
                    mass=item["mass"],
                    radius=item["radius"],
                    position=tuple(item["position"]),
                    velocity=tuple(item["velocity"]),
                    active=item.get("active", True),
                    color=item.get("color", "#40c4ff"),
                    j2=item.get("j2", 0.0),
                    spin_axis=tuple(item.get("spin_axis", (0.0, 0.0, 1.0))),
                    spin_omega=tuple(item.get("spin_omega", (0.0, 0.0, 0.0))),
                )
                for item in raw_bodies
            )
            integrator = IntegratorSettings(**dict(raw_integrator))
            physics = PhysicsSettings(**dict(raw_physics))
            return cls(
                bodies=bodies,  # type: ignore[arg-type]
                current_time=payload.get("current_time", 0.0),
                integrator=integrator,
                physics=physics,
            )
        except (KeyError, TypeError) as exc:
            raise ValueError(f"Incomplete or malformed simulation state: {exc}.") from exc
