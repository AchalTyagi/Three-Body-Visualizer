"""Per-body *visual* size model.

A body has two independent sizes:

* the **physical radius** (``BodyState.radius``) -- used by the physics engine
  for collisions, density, escape velocity and J2; and
* the **visual size** defined here -- used only by the renderer.

Changing a visual size never changes the simulation.  The module imports
neither VTK nor Tk so the rules can be unit-tested headlessly.
"""
from __future__ import annotations

import math
from typing import Any, Iterable, Sequence

import numpy as np

# How the on-screen radius is derived.
SIZE_TRUE = "True scale"          # physical radius x global visual scale
SIZE_MULTIPLIER = "Multiplier"    # physical radius x global visual scale x value
SIZE_FIXED = "Fixed radius"       # absolute world-unit radius, ignores physics and global scale
SIZE_MODES = (SIZE_TRUE, SIZE_MULTIPLIER, SIZE_FIXED)

DEFAULT_SIZE_MODE = SIZE_TRUE
DEFAULT_SIZE_VALUE = 1.0

# Sanity bounds for the user-entered value.
MIN_SIZE_VALUE = 1e-9
MAX_SIZE_VALUE = 1e9

# A body is never drawn smaller than this fraction of the scene span, so a
# realistic-scale planet next to a star stays visible instead of vanishing.
MIN_VISIBLE_FRACTION = 0.008

UNIT_HINTS = {
    SIZE_TRUE: "uses the Radius above",
    SIZE_MULTIPLIER: "× the true-scale size",
    SIZE_FIXED: "radius in scene units",
}


def validate_size(mode: Any, value: Any, label: str = "Body") -> tuple[str, float]:
    """Return a normalised ``(mode, value)`` pair or raise ``ValueError``."""
    if mode not in SIZE_MODES:
        raise ValueError(f"{label} size mode must be one of: {', '.join(SIZE_MODES)}.")
    if isinstance(value, bool):
        raise ValueError(f"{label} size value must be a number.")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{label} size value must be a number.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} size value must be finite.")
    if not MIN_SIZE_VALUE <= number <= MAX_SIZE_VALUE:
        raise ValueError(f"{label} size value must be between {MIN_SIZE_VALUE:g} and {MAX_SIZE_VALUE:g}.")
    return str(mode), number


def display_radius(physical_radius: float, mode: str, value: float,
                   global_scale: float, span: float) -> float:
    """On-screen radius in scene units for one body.

    ``span`` is the current scene extent; it sets the minimum visible size.
    Unknown modes or non-finite inputs fall back to true scale rather than
    raising, because this runs inside the render loop.
    """
    physical = float(physical_radius)
    scale = float(global_scale)
    if not math.isfinite(physical) or physical < 0.0:
        physical = 0.0
    if not math.isfinite(scale) or scale <= 0.0:
        scale = 1.0
    try:
        factor = float(value)
    except (TypeError, ValueError):
        factor = 1.0
    if not math.isfinite(factor) or factor <= 0.0:
        factor = 1.0
    if mode == SIZE_FIXED:
        radius = factor
    elif mode == SIZE_MULTIPLIER:
        radius = physical * scale * factor
    else:
        radius = physical * scale
    floor = max(float(span), 1e-12) * MIN_VISIBLE_FRACTION
    return max(radius, floor)


def default_sizes(count: int = 3) -> list[tuple[str, float]]:
    return [(DEFAULT_SIZE_MODE, DEFAULT_SIZE_VALUE) for _ in range(count)]


def normalise_sizes(sizes: Iterable[Any] | None, count: int = 3,
                    names: Sequence[str] | None = None) -> list[tuple[str, float]]:
    """Validate a list of ``(mode, value)`` pairs or ``{"mode","value"}`` mappings.

    ``None`` or an empty sequence yields defaults (for files written before
    per-body sizes existed).  Anything else must contain exactly ``count``
    valid entries.
    """
    if sizes is None:
        return default_sizes(count)
    items = list(sizes)
    if not items:
        return default_sizes(count)
    if len(items) != count:
        raise ValueError(f"body_sizes must contain exactly {count} entries when provided.")
    result = []
    for index, item in enumerate(items):
        label = names[index] if names and index < len(names) else f"Body {index + 1}"
        if isinstance(item, dict):
            mode, value = item.get("mode", DEFAULT_SIZE_MODE), item.get("value", DEFAULT_SIZE_VALUE)
        else:
            try:
                mode, value = item
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{label} size must be a (mode, value) pair.") from exc
        result.append(validate_size(mode, value, label))
    return result


def sizes_to_payload(sizes: Iterable[tuple[str, float]]) -> list[dict[str, Any]]:
    return [{"mode": mode, "value": float(value)} for mode, value in sizes]


def overlap_warnings(names: Sequence[str], radii: Sequence[float], positions: Sequence[Sequence[float]],
                     active: Sequence[bool] | None = None) -> list[str]:
    """Describe pairs of *physical* radii that already overlap at t = 0.

    Overlapping bodies trigger an immediate collision (merge, bounce, ...), which
    is rarely what a user who is just choosing sizes wants.
    """
    pos = np.asarray(positions, dtype=float).reshape(-1, 3)
    rad = np.asarray(radii, dtype=float).reshape(-1)
    warnings = []
    for i in range(len(rad)):
        for j in range(i + 1, len(rad)):
            if active is not None and not (active[i] and active[j]):
                continue
            distance = float(np.linalg.norm(pos[i] - pos[j]))
            contact = float(rad[i] + rad[j])
            if distance < contact:
                warnings.append(
                    f"{names[i]} and {names[j]} overlap at t = 0 "
                    f"(separation {distance:.4g} < combined radius {contact:.4g}); "
                    f"they will collide immediately.")
    return warnings
