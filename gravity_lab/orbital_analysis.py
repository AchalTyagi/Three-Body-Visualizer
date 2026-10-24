"""Pure helpers for reference frames and pairwise orbital measurements."""
from __future__ import annotations

import numpy as np


def barycentric_frame(positions, velocities, masses, alive, accelerations=None):
    """Return position/velocity (and optional acceleration) relative to live-system COM.

    Dead bodies carry zero weight. If no live positive mass remains, the origin
    defaults to zero and inputs are copied unchanged.
    """
    pos = np.asarray(positions, dtype=float)
    vel = np.asarray(velocities, dtype=float)
    mass = np.where(np.asarray(alive, dtype=bool), np.maximum(np.asarray(masses, dtype=float), 0.0), 0.0)
    total = float(mass.sum())
    if total > 0 and np.isfinite(total):
        origin = np.sum(mass[:, None] * pos, axis=0) / total
        origin_velocity = np.sum(mass[:, None] * vel, axis=0) / total
    else:
        origin = np.zeros(3)
        origin_velocity = np.zeros(3)
    result = [pos - origin, vel - origin_velocity]
    if accelerations is not None:
        acc = np.asarray(accelerations, dtype=float)
        origin_acceleration = np.sum(mass[:, None] * acc, axis=0) / total if total > 0 else np.zeros(3)
        result.append(acc - origin_acceleration)
    return tuple(result)


def pairwise_relative_metrics(positions, velocities, alive):
    """Return { (i,j): (distance, relative_speed) } for active body pairs."""
    pos = np.asarray(positions, dtype=float)
    vel = np.asarray(velocities, dtype=float)
    live = np.asarray(alive, dtype=bool)
    metrics = {}
    for i in range(len(live)):
        if not live[i]:
            continue
        for j in range(i + 1, len(live)):
            if not live[j]:
                continue
            distance = float(np.linalg.norm(pos[j] - pos[i]))
            speed = float(np.linalg.norm(vel[j] - vel[i]))
            if np.isfinite(distance) and np.isfinite(speed):
                metrics[(i, j)] = (distance, speed)
    return metrics
