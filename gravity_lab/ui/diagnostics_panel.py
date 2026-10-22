"""Reusable diagnostic plotting widgets and defensive formatting helpers.

The plotting widgets use Tk Canvas rather than a separate plotting backend so
that diagnostic rendering remains lightweight and themeable.
"""
from __future__ import annotations

import math
import tkinter as tk
from typing import Iterable, Sequence

import numpy as np

from ..themes import THEMES


def format_finite(value: object, spec: str = ".2e", unavailable: str = "N/A") -> str:
    """Format a numeric diagnostic only when its value is finite."""
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return unavailable
    if not math.isfinite(number):
        return unavailable
    return format(number, spec)


def minimum_active_pair_separation(positions: object, active: object) -> float | None:
    """Return the smallest finite separation for an active pair, or ``None``.

    ``None`` means there is no valid active pair (e.g. after two bodies merge)
    or that the state data is malformed/non-finite. It is displayed as N/A
    instead of leaking a NaN into the status bar.
    """
    try:
        pos = np.asarray(positions, dtype=float)
        mask = np.asarray(active, dtype=bool)
    except (TypeError, ValueError):
        return None
    if pos.shape != (3, 3) or mask.shape != (3,):
        return None
    distances: list[float] = []
    for i in range(3):
        if not mask[i] or not np.all(np.isfinite(pos[i])):
            continue
        for j in range(i + 1, 3):
            if not mask[j] or not np.all(np.isfinite(pos[j])):
                continue
            distance = float(np.linalg.norm(pos[j] - pos[i]))
            if math.isfinite(distance):
                distances.append(distance)
    return min(distances) if distances else None


class SparkGraph(tk.Canvas):
    """Small interactive time-series chart with axis labels and event markers."""

    def __init__(self, master, title: str, colors: Sequence[str], *, height: int = 210, **kwargs):
        super().__init__(master, height=height, highlightthickness=1, **kwargs)
        self.title = title
        self.colors = tuple(colors) or ("#9fb3c8",)
        self.data: list[np.ndarray] = []
        self.labels: list[str] = []
        self.x_values: np.ndarray | None = None
        self.event_times: tuple[float, ...] = ()
        self.logarithmic = False
        self.x_label = "Time"
        self.y_label = "Value"
        self.palette = THEMES["Dark"]
        self.bind("<Configure>", lambda _event: self.redraw())
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", lambda _event: self.delete("hover"))

    def set_theme(self, palette: dict) -> None:
        self.palette = palette
        self.configure(background=palette["panel_bg"], highlightbackground=palette["border"])
        self.redraw()

    def set_data(self, series: Iterable[Iterable[float]], labels=None, logarithmic: bool = False,
                 x_values: Iterable[float] | None = None, x_label: str = "Time",
                 y_label: str = "Value", event_times: Iterable[float] = ()) -> None:
        arrays = []
        for values in series:
            try:
                arrays.append(np.asarray(list(values), dtype=float))
            except (TypeError, ValueError):
                arrays.append(np.asarray([], dtype=float))
        self.data = arrays
        self.labels = list(labels or [])
        self.logarithmic = bool(logarithmic)
        self.x_label = x_label
        self.y_label = y_label
        try:
            x = np.asarray(list(x_values), dtype=float) if x_values is not None else None
        except (TypeError, ValueError):
            x = None
        expected = max((len(a) for a in arrays), default=0)
        self.x_values = x if x is not None and len(x) == expected and np.all(np.isfinite(x)) else None
        try:
            self.event_times = tuple(float(t) for t in event_times if math.isfinite(float(t)))
        except (TypeError, ValueError, OverflowError):
            self.event_times = ()
        self.redraw()

    def _transformed(self, values: np.ndarray) -> np.ndarray:
        if not self.logarithmic:
            return values.copy()
        result = values.copy()
        valid = np.isfinite(result)
        result[valid] = np.log10(np.maximum(result[valid], 1e-16))
        return result

    def redraw(self) -> None:
        self.delete("all")
        width, height = max(self.winfo_width(), 160), max(self.winfo_height(), 90)
        palette = self.palette
        left, right, top, bottom = 48, width - 14, 44, height - 32
        if right <= left + 20 or bottom <= top + 20:
            return
        self.create_text(10, 7, text=self.title, anchor="nw", fill=palette["text"],
                         font=("Segoe UI", 9, "bold"))
        self.create_line(left, top, left, bottom, fill=palette["border"])
        self.create_line(left, bottom, right, bottom, fill=palette["border"])
        self.create_text((left + right) / 2, height - 7, text=self.x_label, fill=palette["muted"],
                         font=("Segoe UI", 7))
        self.create_text(9, (top + bottom) / 2, text=self.y_label, fill=palette["muted"],
                         font=("Segoe UI", 7), angle=90)

        usable = [a for a in self.data if len(a) >= 2]
        if not usable:
            message = "No valid samples yet" if self.data else "Waiting for simulation history"
            self.create_text((left + right) / 2, (top + bottom) / 2, text=message,
                             fill=palette["muted"], font=("Segoe UI", 9))
            return

        transformed = [self._transformed(a) for a in self.data]
        vals = np.concatenate([a[np.isfinite(a)] for a in transformed if np.any(np.isfinite(a))]) if any(
            np.any(np.isfinite(a)) for a in transformed
        ) else np.asarray([], dtype=float)
        if vals.size == 0:
            self.create_text((left + right) / 2, (top + bottom) / 2, text="No finite data available",
                             fill=palette["muted"], font=("Segoe UI", 9))
            return
        ymin, ymax = float(np.min(vals)), float(np.max(vals))
        if math.isclose(ymin, ymax, rel_tol=1e-12, abs_tol=1e-15):
            padding = max(abs(ymin) * 0.08, 0.5 if self.logarithmic else 1e-6)
            ymin -= padding
            ymax += padding
        pad = (ymax - ymin) * 0.08
        ymin, ymax = ymin - pad, ymax + pad
        self.create_text(left - 5, top, text=f"{ymax:.2g}", anchor="e", fill=palette["muted"], font=("Segoe UI", 7))
        self.create_text(left - 5, bottom, text=f"{ymin:.2g}", anchor="e", fill=palette["muted"], font=("Segoe UI", 7))

        max_n = max(len(a) for a in self.data)
        if self.x_values is not None:
            x_source = self.x_values
        else:
            x_source = np.arange(max_n, dtype=float)
        x_finite = x_source[np.isfinite(x_source)]
        if x_finite.size == 0:
            x_min, x_max = 0.0, float(max(max_n - 1, 1))
        else:
            x_min, x_max = float(np.min(x_finite)), float(np.max(x_finite))
            if math.isclose(x_min, x_max):
                x_min -= 0.5
                x_max += 0.5

        # Collision/merge/impact event markers are shared by all time-series tabs.
        for event_t in self.event_times:
            if x_min <= event_t <= x_max:
                x = left + (event_t - x_min) / (x_max - x_min) * (right - left)
                self.create_line(x, top, x, bottom, fill=palette["accent"], dash=(3, 3), tags=("event_mark",))
                self.create_polygon(x - 3, top, x + 3, top, x, top + 5,
                                    fill=palette["accent"], outline="", tags=("event_mark",))

        for index, values in enumerate(transformed):
            if len(values) < 2:
                continue
            n = len(values)
            xs_data = x_source if len(x_source) == n else np.arange(n, dtype=float)
            xs = left + (xs_data - x_min) / (x_max - x_min) * (right - left)
            ys = bottom - (values - ymin) / (ymax - ymin) * (bottom - top)
            valid = np.isfinite(values) & np.isfinite(xs_data)
            points: list[float] = []
            for x, y, ok in zip(xs, ys, valid):
                if ok:
                    points.extend((float(x), float(y)))
                else:
                    if len(points) >= 4:
                        self.create_line(*points, fill=self.colors[index % len(self.colors)], width=1.6,
                                         smooth=False, tags=(f"series_{index}",))
                    points = []
            if len(points) >= 4:
                self.create_line(*points, fill=self.colors[index % len(self.colors)], width=1.6,
                                 smooth=False, tags=(f"series_{index}",))

        if x_source.size:
            x_start = format(float(x_min), ".3g")
            x_end = format(float(x_max), ".3g")
            self.create_text(left, bottom + 10, text=x_start, anchor="n", fill=palette["muted"], font=("Segoe UI", 7))
            self.create_text(right, bottom + 10, text=x_end, anchor="n", fill=palette["muted"], font=("Segoe UI", 7))
        if self.labels:
            x, y = left + 4, 28
            for i, label in enumerate(self.labels):
                color = self.colors[i % len(self.colors)]
                self.create_line(x, y, x + 12, y, fill=color, width=2)
                self.create_text(x + 16, y, text=label, anchor="w", fill=palette["muted"], font=("Segoe UI", 7))
                x += max(64, min(110, len(label) * 5 + 30))

    def _on_motion(self, event) -> None:
        if not self.data:
            return
        values = [a for a in self.data if len(a)]
        if not values:
            return
        width = max(self.winfo_width(), 160)
        left, right = 48, width - 14
        fraction = min(1.0, max(0.0, (event.x - left) / max(1, right - left)))
        count = max((len(a) for a in values), default=0)
        if count == 0:
            return
        index = min(count - 1, max(0, round(fraction * (count - 1))))
        parts = []
        if self.x_values is not None and index < len(self.x_values):
            parts.append(f"t={format_finite(self.x_values[index], '.5g')}")
        for label, series in zip(self.labels, self.data):
            if index < len(series):
                val = format_finite(series[index], ".4g")
                parts.append(f"{label}: {val}")
        if not parts:
            return
        label_text = "   |   ".join(parts)
        palette = self.palette
        x = max(65, min(width - 120, event.x + 12))
        y = max(40, event.y - 12)
        self.delete("hover")
        text_id = self.create_text(x, y, text=label_text, anchor="nw", fill=palette["text"],
                                   font=("Segoe UI", 8), tags=("hover",))
        bbox = self.bbox(text_id)
        if bbox:
            rect = self.create_rectangle(bbox[0] - 4, bbox[1] - 2, bbox[2] + 4, bbox[3] + 2,
                                         fill=palette["panel_bg"], outline=palette["border"], tags=("hover",))
            self.tag_lower(rect, text_id)
