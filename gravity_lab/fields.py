"""Numerical 2D slice of the combined 3D gravitational acceleration field."""
from __future__ import annotations
import numpy as np


def field_magnitude_grid(x_grid, y_grid, z_slice, masses, positions, G, softening,
                         *, enable_oblateness=False, j2=None, spin_axes=None, radii=None):
    """Return |g| across an XY grid at fixed z, in simulation acceleration units.

    The optional J2 contribution matches the engine's fixed-spin-axis exterior
    zonal-harmonic approximation. Velocity-dependent 1PN/tidal terms are not
    part of a static gravitational-field map.
    """
    grid = np.stack((x_grid, y_grid, np.full_like(x_grid, z_slice)), axis=-1)
    delta = np.asarray(positions)[None, None, :, :] - grid[:, :, None, :]
    r2 = np.einsum("...k,...k->...", delta, delta) + float(softening) ** 2
    r2 = np.maximum(r2, 1e-24)
    mass_array = np.asarray(masses, dtype=float)
    position_array = np.asarray(positions, dtype=float)
    acc = float(G) * np.sum(mass_array[None, None, :, None] * delta / r2[..., None] ** 1.5, axis=2)
    if enable_oblateness and j2 is not None and spin_axes is not None and radii is not None and float(G) > 0:
        coeffs = np.asarray(j2, dtype=float).reshape(3)
        axes = np.asarray(spin_axes, dtype=float).reshape(3, 3)
        radii_array = np.asarray(radii, dtype=float).reshape(3)
        axes = axes / np.maximum(np.linalg.norm(axes, axis=1)[:, None], 1e-15)
        for j in range(3):
            if coeffs[j] == 0 or mass_array[j] <= 0 or radii_array[j] <= 0:
                continue
            rvec = grid - position_array[j]
            rr2 = np.einsum("...k,...k->...", rvec, rvec)
            rr = np.sqrt(np.maximum(rr2, 1e-24))
            z = np.einsum("...k,k->...", rvec, axes[j])
            factor = 1.5 * float(G) * mass_array[j] * coeffs[j] * radii_array[j]**2 / rr**5
            corr = ((5.0 * z*z / np.maximum(rr2, 1e-24) - 1.0)[..., None] * rvec
                    - 2.0 * z[..., None] * axes[j])
            # The J2 formula is only applied outside the source's physical radius.
            corr = np.where((rr >= radii_array[j])[..., None], factor[..., None] * corr, 0.0)
            acc += corr
    return np.linalg.norm(acc, axis=-1)
