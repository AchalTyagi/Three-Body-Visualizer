# Simulation service API

`gravity_lab.service` is the application boundary between validated `SimulationState` and the mutable `ThreeBodyEngine`. It has no Tkinter or VTK imports and can be tested in a headless Python process.

## Public API

- `engine_from_state(state) -> ThreeBodyEngine` materializes a validated model into the numerical engine. It preserves body metadata separately from the engine's numerical arrays.
- `SimulationService.reset(state) -> SimulationSnapshot` starts a fresh engine at the state's positions, velocities, settings, active mask, and current time. Diagnostic baselines are recalculated for that initial state.
- `SimulationService.advance(...) -> SimulationSnapshot` advances a frame using the current integrator settings or explicit overrides for the existing speed control.
- `SimulationService.step(h, method) -> SimulationSnapshot` advances one specified model-time interval.
- `SimulationService.snapshot() -> SimulationSnapshot` returns an immutable record of current positions/velocities, activity, conserved quantities, finite diagnostics, separation, events and integrator counters.
- `SimulationService.state` exposes the last validated immutable state updated from a healthy engine state.

## Example

```python
from gravity_lab.service import SimulationService
from gravity_lab.state import BodyState, IntegratorSettings, PhysicsSettings, SimulationState
from gravity_lab.physics import PASS, YOSHIDA

state = SimulationState(
    bodies=(
        BodyState("A", 1.0, 0.02, (-1.0, 0.0, 0.0), (0.0, -0.2, 0.0)),
        BodyState("B", 1.0, 0.02, (1.0, 0.0, 0.0), (0.0, 0.2, 0.0)),
        BodyState("C", 0.1, 0.01, (0.0, 1.5, 0.0), (0.2, 0.0, 0.0)),
    ),
    integrator=IntegratorSettings(method=YOSHIDA, dt=0.001, steps_per_frame=4),
    physics=PhysicsSettings(collision_mode=PASS),
)

service = SimulationService(state)
frame = service.advance()
print(frame.time, frame.minimum_separation, frame.energy_error)
```

## Migration note

The VTK renderer and history collector still read the engine directly during this incremental migration. The `engine` property is explicitly a compatibility escape hatch, not the intended long-term interface. Future changes should pass snapshots to rendering and diagnostics so widgets cannot mutate physics state. The existing schema-1 setup JSON remains unchanged; this state mapping is not yet a stable checkpoint format.

## Inactive body slots

`SimulationState` retains positive body mass/radius records for inactive slots. This avoids losing body identity and display metadata after a merge. The engine may set a removed body's mass/radius to zero internally; the service snapshot reflects those engine arrays, while the explicit state keeps a valid record with `active=False`.

## Controller and persistence extensions

- `SimulationController.activate_preset(name, ...)` converts a built-in preset into a validated `SimulationState` and resets the service.
- `SimulationController.apply_inputs(values, ...)` builds and validates a state from parsed numeric form values without importing Tkinter.
- `SimulationService.render_frame()` returns a read-only `SceneFrame` for VTK presentation. This is a renderer data adapter, not a second physics engine.
- `save_checkpoint(service, path)` and `load_checkpoint(path)` in `gravity_lab.state_io` provide atomic, checksummed, versioned checkpoint persistence. Legacy setup JSON is intentionally a separate user-interface preference/configuration format.
