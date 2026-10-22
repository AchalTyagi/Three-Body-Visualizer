# Physics Foundation Update

This update starts the Gravity Lab 3D physics roadmap with a focus on the Newtonian force model, collision events, integrator accuracy, and reproducible validation.

## 1. Exact Newtonian gravity by default

All built-in presets now use `softening = 0.0`. For non-overlapping bodies, the engine uses the inverse-square point-mass field:

\[
\mathbf a_i = G\sum_{j\ne i} m_j\,\frac{\mathbf r_j-\mathbf r_i}{|\mathbf r_j-\mathbf r_i|^3}.
\]

The `Softening ε (0 = Newtonian)` field remains available. Any non-zero value deliberately changes the force law to a Plummer-softened model. Body radii do not alter the exterior field of a spherical body; they define the contact distance for the collision model.

## 2. Collision-time handling

The engine estimates contact time from relative position and velocity, approaches predicted contact using shorter substeps, and uses swept-segment contact detection as a fallback if bodies cross between step endpoints. This prevents common high-speed collision tunneling cases and is covered for both Velocity Verlet and RK45.

This remains an event-location approximation for accelerated trajectories, not a closed-form collision solution. Difficult close encounters should be run with RK45, sensible tolerances, and convergence checks. `Pass through` is an idealized option; with zero softening, an exact center-to-center coincidence is singular under point-mass Newtonian gravity.

## 3. Error-controlled RK45

The new Dormand–Prince 5(4) option automatically adapts its internal substep size using relative and absolute error tolerances. The GUI exposes `RK45 relative tolerance` and `RK45 absolute tolerance` and reports accepted/rejected steps plus the last local error estimate.

- **Yoshida (4th order, symplectic):** a good choice for efficient long conservative integrations with fixed step size.
- **Velocity Verlet (2nd order):** simple and useful for comparison.
- **Dormand–Prince RK45:** a high-accuracy adaptive option for changing trajectories and reference comparisons.

Variable time steps generally weaken the strict symplectic property of Yoshida; use the integrator that fits the problem rather than expecting one method to be best for every orbit.

## 4. Validation additions

The self-test suite now covers:

- exact inverse-square acceleration at zero softening;
- high-speed impacts that would tunnel through bodies without event handling;
- linear momentum through elastic impacts;
- orbit closure at two Yoshida step sizes;
- orbit closure at two RK45 relative tolerances;
- previously existing conservation, collision bookkeeping, close-encounter, astronomical-unit, and field-map tests.

Run:

```bash
python main.py --selftest
python -m pytest -q
```

The GUI also has **Run physics validation…**, which presents the current test report in a dialog.
