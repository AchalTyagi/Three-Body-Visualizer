# Phase 8 — JPL Horizons Improvements

- Horizons import validates calendar dates and times before making a network request.
- The import dialog identifies the TDB epoch, coordinate convention, and units.
- Fetching states opens a review table with masses, physical radii, positions, and velocities before the user applies them.
- Applying states is explicit and warns that only the selected trio is subsequently simulated; omitted planets are not retained as perturbing bodies.
- The comparison of later Horizons samples against simulated trajectories remains a follow-up item; it requires a carefully defined propagation duration and coordinate transformation so the comparison is scientifically meaningful.

Validation: date/time normalization and invalid epoch rejection are covered by unit tests. Network access is required for live Horizons retrieval.
