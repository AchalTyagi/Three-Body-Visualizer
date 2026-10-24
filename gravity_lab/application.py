"""GUI-independent application orchestration for presets and simulation actions."""
from __future__ import annotations

from typing import Mapping, Sequence

from .body_size import normalise_sizes
from .physics import INTEGRATORS, MERGE, YOSHIDA
from .presets import PRESETS, ARBITRARY
from .service import SimulationService, SimulationSnapshot
from .state import BodyState, IntegratorSettings, PhysicsSettings, SimulationState


def state_from_preset(
    name: str,
    presets: Mapping[str, Mapping[str, object]] | None = None,
    *,
    body_names: Sequence[str] | None = None,
    body_colors: Sequence[str] | None = None,
) -> SimulationState:
    """Convert a built-in preset into a validated, UI-independent state model."""
    catalog = PRESETS if presets is None else presets
    if name not in catalog:
        raise KeyError(f"Unknown preset: {name!r}.")
    preset = catalog[name]
    raw_bodies = preset.get("bodies")
    if not isinstance(raw_bodies, Sequence) or len(raw_bodies) != 3:
        raise ValueError(f"Preset {name!r} must define exactly three bodies.")
    names = list(body_names or ("Body 1", "Body 2", "Body 3"))
    colors = list(body_colors or ("#40c4ff", "#ff6685", "#ffd166"))
    if len(names) != 3 or len(colors) != 3:
        raise ValueError("Exactly three body names and colours are required.")
    bodies = []
    for index, row in enumerate(raw_bodies):
        if not isinstance(row, Sequence) or len(row) != 8:
            raise ValueError(f"Preset {name!r}, body {index + 1} must contain mass, radius, position and velocity.")
        bodies.append(BodyState(
            name=str(names[index]), mass=float(row[0]), radius=float(row[1]),
            position=tuple(float(v) for v in row[2:5]),
            velocity=tuple(float(v) for v in row[5:8]), color=str(colors[index]),
        ))
    method = str(preset.get("integrator", YOSHIDA))
    if method not in INTEGRATORS:
        raise ValueError(f"Preset {name!r} specifies an unknown integrator {method!r}.")
    integrator = IntegratorSettings(
        method=method, dt=float(preset.get("dt", 0.003)),
        steps_per_frame=int(preset.get("steps", 4)),
        adaptive=bool(preset.get("adaptive", False)), rtol=1e-9, atol=1e-12,
    )
    physics = PhysicsSettings(
        gravitational_constant=float(preset.get("G", 1.0)),
        softening=float(preset.get("soft", 0.0)),
        collision_mode=str(preset.get("collision", MERGE)),
        units=str(preset.get("units", ARBITRARY)),
    )
    return SimulationState(tuple(bodies), 0.0, integrator, physics)  # type: ignore[arg-type]


def state_from_inputs(
    values: Mapping[str, object], *, body_names: Sequence[str], body_colors: Sequence[str],
    units: str, integrator_method: str, adaptive: bool,
    body_sizes: Sequence[object] | None = None,
) -> SimulationState:
    """Validate parsed GUI values and construct the domain model outside widgets."""
    if len(body_names) != 3 or len(body_colors) != 3:
        raise ValueError("Exactly three body names and colours are required.")
    sizes = normalise_sizes(body_sizes, 3, [str(n).strip() or f"Body {i + 1}" for i, n in enumerate(body_names)])
    try:
        bodies = tuple(BodyState(
            name=str(body_names[i]).strip() or f"Body {i + 1}",
            mass=float(values["m"][i]), radius=float(values["R"][i]),
            position=tuple(float(v) for v in values["pos"][i]),
            velocity=tuple(float(v) for v in values["vel"][i]),
            color=str(body_colors[i]), j2=float(values["j2"][i]),
            spin_axis=tuple(float(v) for v in values["spin_axes"][i]),
            spin_omega=tuple(float(v) for v in values["spin_omega"][i]),
            size_mode=sizes[i][0], size_value=sizes[i][1],
        ) for i in range(3))
        integrator = IntegratorSettings(
            method=integrator_method, dt=float(values["dt"]),
            steps_per_frame=int(values["steps"]), adaptive=bool(adaptive),
            rtol=float(values["rtol"]), atol=float(values["atol"]),
        )
        physics = PhysicsSettings(
            gravitational_constant=float(values["G"]), softening=float(values["soft"]),
            collision_mode=str(values["collision"]), restitution=float(values["restitution"]),
            units=str(units), enable_oblateness=bool(values["enable_oblateness"]),
            enable_1pn=bool(values["enable_1pn"]), c_light=float(values["c_light"]),
            tidal_damping=float(values["tidal_damping"]),
        )
    except (KeyError, TypeError, IndexError, OverflowError) as exc:
        raise ValueError(f"Simulation inputs are incomplete or malformed: {exc}.") from exc
    return SimulationState(bodies, 0.0, integrator, physics)  # type: ignore[arg-type]


class SimulationController:
    """Command boundary between GUI actions and simulation state changes."""

    def __init__(self, service: SimulationService | None = None):
        self.service = service or SimulationService()

    @property
    def state(self) -> SimulationState | None:
        return self.service.state

    def activate_preset(self, name: str, **kwargs) -> SimulationSnapshot:
        return self.service.reset(state_from_preset(name, **kwargs))

    def apply_state(self, state: SimulationState) -> SimulationSnapshot:
        if not isinstance(state, SimulationState):
            raise TypeError("apply_state requires a validated SimulationState.")
        return self.service.reset(state)

    def apply_inputs(self, values: Mapping[str, object], **options) -> SimulationSnapshot:
        """Build a validated state from parsed form values and reset the service."""
        return self.apply_state(state_from_inputs(values, **options))

    def advance(self, **kwargs) -> SimulationSnapshot:
        return self.service.advance(**kwargs)
