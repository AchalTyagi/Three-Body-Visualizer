"""Camera maths for the Gravity Lab viewport.

This module deliberately imports neither VTK nor Tk so the zoom/follow
behaviour can be unit-tested headlessly.  The UI layer reads the VTK camera,
calls these helpers, and writes the result back.
"""
from __future__ import annotations

import math
from typing import Optional, Tuple

import numpy as np

# One wheel notch changes the view scale by this factor.
WHEEL_STEP = 1.15
# Windows/X11 report 120 units per notch; precision touchpads report fractions
# of that.  macOS Tk reports small integers (about 1 per tick).
WINDOWS_NOTCH = 120.0
MACOS_NOTCH = 1.0
# A single fast flick must not teleport the camera.
MAX_NOTCHES_PER_EVENT = 4.0

# Allowed camera distance / parallel scale, as multiples of the scene extent.
MIN_DISTANCE_FRACTION = 1e-3
MAX_DISTANCE_FRACTION = 80.0
MIN_SCALE_FRACTION = 1e-3
MAX_SCALE_FRACTION = 40.0


def wheel_zoom_factor(delta: Optional[float] = None, direction: Optional[int] = None,
                      notch_size: float = WINDOWS_NOTCH, step: float = WHEEL_STEP) -> float:
    """Return a zoom factor (>1 zooms in, <1 zooms out, 1 means no change).

    ``delta`` is a Tk ``event.delta``; ``direction`` (+1/-1) is used for X11
    Button-4/5 events, which carry no delta.  Zoom is exponential in the number
    of notches, so two half-notches equal one full notch and zooming in then
    out by the same amount returns exactly to the starting view.
    """
    if delta is not None and delta != 0 and math.isfinite(delta):
        notches = float(delta) / max(float(notch_size), 1e-9)
        # Never let a tiny touchpad delta round to zero movement, and never
        # let a huge one jump more than a few notches.
        notches = max(-MAX_NOTCHES_PER_EVENT, min(MAX_NOTCHES_PER_EVENT, notches))
    elif direction:
        notches = 1.0 if direction > 0 else -1.0
    else:
        return 1.0
    return float(step) ** notches


def zoom_limits(extent: float) -> Tuple[float, float, float, float]:
    """(min_distance, max_distance, min_scale, max_scale) for a scene extent."""
    extent = max(float(extent), 1e-9)
    return (extent * MIN_DISTANCE_FRACTION, extent * MAX_DISTANCE_FRACTION,
            extent * MIN_SCALE_FRACTION, extent * MAX_SCALE_FRACTION)


def zoom_about_point(position, focal, anchor, factor: float, parallel: bool,
                     parallel_scale: float, extent: float):
    """Zoom so the world point ``anchor`` (on the focal plane) stays put on screen.

    Works for both projections:

    * perspective: the camera moves toward/away from the focal point;
    * parallel (the 2D view): ``Dolly`` does nothing visually, so the
      parallel scale is changed instead.

    Zoom is clamped to sensible limits.  When a limit is hit the effective
    factor shrinks to what is actually possible, and when no zoom is possible
    the camera is returned unchanged -- so scrolling against a limit no longer
    drifts the view sideways.

    Returns ``(position, focal, parallel_scale, applied_factor)``.
    """
    position = np.asarray(position, dtype=float)
    focal = np.asarray(focal, dtype=float)
    anchor = np.asarray(anchor, dtype=float)
    factor = float(factor)
    if not (math.isfinite(factor) and factor > 0.0) or not np.all(np.isfinite(anchor)):
        return position, focal, float(parallel_scale), 1.0

    min_d, max_d, min_s, max_s = zoom_limits(extent)
    if parallel:
        old = max(float(parallel_scale), 1e-12)
        new = min(max(old / factor, min_s), max_s)
        applied = old / new
        new_scale = new
    else:
        old = max(float(np.linalg.norm(position - focal)), 1e-12)
        new = min(max(old / factor, min_d), max_d)
        applied = old / new
        new_scale = float(parallel_scale)

    if abs(applied - 1.0) < 1e-12:
        return position, focal, float(parallel_scale), 1.0

    shift = (anchor - focal) * (1.0 - 1.0 / applied)
    new_focal = focal + shift
    if parallel:
        new_position = position + shift
    else:
        new_position = new_focal + (position - focal) / applied
    return new_position, new_focal, new_scale, applied


def recentre(position, focal, target):
    """Translate the camera rig so ``focal`` lands on ``target``.

    Orbit angle and zoom distance are preserved; only the pan offset is removed.
    """
    position = np.asarray(position, dtype=float)
    focal = np.asarray(focal, dtype=float)
    target = np.asarray(target, dtype=float)
    delta = target - focal
    if not np.all(np.isfinite(delta)):
        return position, focal
    return position + delta, target.copy()


def follow_translation(target, previous_target, focal):
    """Translation that keeps the camera locked to a moving target.

    On the first frame after locking (``previous_target is None``) the focal
    point is brought onto the target.  Afterwards only the target's own
    displacement is applied, which preserves the user's orbit/zoom/pan offset.
    Returns a zero vector for non-finite input.
    """
    target = np.asarray(target, dtype=float)
    reference = np.asarray(focal if previous_target is None else previous_target, dtype=float)
    delta = target - reference
    if not np.all(np.isfinite(delta)):
        return np.zeros(3)
    return delta


# ---------------------------------------------------------------------------
# Mouse-drag routing and panning
# ---------------------------------------------------------------------------
DRAG_ORBIT = "orbit"   # hand the drag to the VTK trackball style (3D only)
DRAG_PAN = "pan"       # translate the camera in the view plane
DRAG_ZOOM = "zoom"     # vertical drag zooms
DRAG_NONE = None

# Fraction of the view zoomed per pixel of vertical right-drag.
DRAG_ZOOM_RATE = 0.01


def drag_action(view_mode: str, button: int, shift: bool = False, ctrl: bool = False) -> Optional[str]:
    """Decide what a mouse drag does.

    2D view (orthographic top-down XY): the plane must never rotate.
        left / middle drag -> pan, right drag -> zoom.
    3D view: left drag orbits; middle drag or Shift+left pans (so laptops
        without a middle button can pan); right drag zooms.
    """
    is_2d = str(view_mode).strip().upper() == "2D"
    if button == 3:
        return DRAG_ZOOM
    if button == 2:
        return DRAG_PAN
    if button == 1:
        if is_2d or shift or ctrl:
            return DRAG_PAN
        return DRAG_ORBIT
    return DRAG_NONE


def drag_zoom_factor(dy_pixels: float, rate: float = DRAG_ZOOM_RATE) -> float:
    """Zoom factor for a vertical drag: dragging up zooms in, down zooms out."""
    if not math.isfinite(dy_pixels):
        return 1.0
    return math.exp(-float(dy_pixels) * float(rate))


def pan_translation(dx_pixels: float, dy_pixels: float, viewport_height_pixels: float,
                    position, focal, view_up, parallel: bool, parallel_scale: float,
                    view_angle_degrees: float = 30.0):
    """World-space translation to apply to *both* camera position and focal point.

    A drag of (dx, dy) pixels (Tk convention: +x right, +y down) moves the scene
    with the cursor, i.e. the camera moves the opposite way.  The scale is the
    world distance covered by one pixel on the focal plane, so the point under
    the cursor stays under the cursor in both projections.
    """
    position = np.asarray(position, dtype=float)
    focal = np.asarray(focal, dtype=float)
    up = np.asarray(view_up, dtype=float)
    height = max(float(viewport_height_pixels), 1.0)
    direction = focal - position
    distance = float(np.linalg.norm(direction))
    if distance < 1e-15 or not (math.isfinite(dx_pixels) and math.isfinite(dy_pixels)):
        return np.zeros(3)
    direction = direction / distance
    right = np.cross(direction, up)
    right_norm = float(np.linalg.norm(right))
    if right_norm < 1e-12:
        return np.zeros(3)
    right = right / right_norm
    true_up = np.cross(right, direction)
    if parallel:
        world_per_pixel = 2.0 * float(parallel_scale) / height
    else:
        world_per_pixel = 2.0 * distance * math.tan(math.radians(float(view_angle_degrees)) / 2.0) / height
    return (-float(dx_pixels) * right + float(dy_pixels) * true_up) * world_per_pixel
