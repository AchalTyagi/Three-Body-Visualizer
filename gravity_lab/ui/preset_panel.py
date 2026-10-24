"""Preset selector and starting-system information panel."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..presets import PRESET_NAMES, PRESETS


def filter_preset_names(query: str, preset_names, presets, custom_preset: str) -> list[str]:
    """Filter presets by name, family, or descriptive metadata, preserving order."""
    needle = str(query).strip().casefold()
    choices = [custom_preset]
    for name in preset_names:
        metadata = presets.get(name, {})
        searchable = " ".join((name, str(metadata.get("description", "")),
                               str(metadata.get("family", "")))).casefold()
        if not needle or needle in searchable:
            choices.append(name)
    return choices


def build_preset_panel(app, side, *, custom_preset: str) -> None:
    side = app.side_inner
    ttk.Label(side, text="SIMULATION SETUP", style="Panel.TLabel", font=("Segoe UI", 12, "bold")).pack(anchor="w")
    ttk.Label(side, text="Edit the bodies, then apply and reset. Drag to rotate; scroll to zoom.",
              style="Panel.TLabel", wraplength=360).pack(anchor="w", pady=(2, 8))

    preset_box = ttk.LabelFrame(side, text="Starting system", padding=7)
    preset_box.pack(fill=tk.X, pady=(0, 7))
    ttk.Label(preset_box, text="Search presets", style="Sub.TLabel").pack(anchor="w", pady=(0, 2))
    app.preset_search_var = tk.StringVar(value="")
    search_entry = ttk.Entry(preset_box, textvariable=app.preset_search_var)
    search_entry.pack(fill=tk.X, pady=(0, 5))

    app.preset_combo = ttk.Combobox(
        preset_box,
        textvariable=app.preset_var,
        values=[custom_preset, *PRESET_NAMES],
        state="readonly",
    )
    app.preset_combo.pack(fill=tk.X)
    app.preset_combo.bind("<<ComboboxSelected>>", app._on_preset_selected)

    def filter_presets(*_args):
        choices = filter_preset_names(app.preset_search_var.get(), PRESET_NAMES, PRESETS, custom_preset)
        app.preset_combo.configure(values=choices)

    app.preset_search_var.trace_add("write", filter_presets)
    ttk.Button(
        preset_box,
        text="＋ Build a new custom model",
        command=app._start_custom_model,
    ).pack(fill=tk.X, pady=(5, 0))
    ttk.Label(preset_box, textvariable=app.preset_info_var, style="Sub.TLabel",
              wraplength=365, justify=tk.LEFT).pack(anchor="w", pady=(5, 0))
