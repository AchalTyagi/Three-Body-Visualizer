"""Preset selector and starting-system information panel."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..presets import PRESET_NAMES


def build_preset_panel(app, side, *, custom_preset: str) -> None:
    side = app.side_inner
    ttk.Label(side, text="SIMULATION SETUP", style="Panel.TLabel", font=("Segoe UI", 12, "bold")).pack(anchor="w")
    ttk.Label(side, text="Edit the bodies, then apply and reset. Drag to rotate; scroll to zoom.",
              style="Panel.TLabel", wraplength=360).pack(anchor="w", pady=(2, 8))

    preset_box = ttk.LabelFrame(side, text="Starting system", padding=7)
    preset_box.pack(fill=tk.X, pady=(0, 7))
    app.preset_combo = ttk.Combobox(
        preset_box,
        textvariable=app.preset_var,
        values=[custom_preset, *PRESET_NAMES],
        state="readonly",
    )
    app.preset_combo.pack(fill=tk.X)
    app.preset_combo.bind("<<ComboboxSelected>>", app._on_preset_selected)
    ttk.Button(
        preset_box,
        text="＋ Build a new custom model",
        command=app._start_custom_model,
    ).pack(fill=tk.X, pady=(5, 0))
    ttk.Label(preset_box, textvariable=app.preset_info_var, style="Sub.TLabel",
              wraplength=365, justify=tk.LEFT).pack(anchor="w", pady=(5, 0))
