"""Body editor and simulation-settings panels for the main window."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..body_size import SIZE_MODES
from ..physics import INTEGRATORS, COLLISION_MODES, ZONE_MODES
from ..presets import ARBITRARY, ASTRO


def build_body_editor_panel(app, side) -> None:
    app.body_color_buttons = []
    app.body_cards = []
    app.body_size_entries = []
    for i, var_row in enumerate(app.body_vars):
        card = ttk.LabelFrame(side, text=f"BODY {i + 1} · {app.body_name_vars[i].get()}",
                              style=f"Body{i+1}.TLabelframe", padding=7)
        card.pack(fill=tk.X, pady=4)
        app.body_cards.append(card)

        identity = ttk.Frame(card, style="Panel.TFrame")
        identity.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(identity, text="Name", style="Panel.TLabel").pack(side=tk.LEFT, padx=(0, 5))
        name_entry = ttk.Entry(identity, textvariable=app.body_name_vars[i], width=14)
        name_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        color_button = tk.Button(
            identity, text="Customize Body", command=lambda idx=i: app._customize_body(idx),
            foreground=app.body_colors[i], background=app.palette["panel_bg"],
            activeforeground=app.body_colors[i], activebackground=app.palette["button_active"],
            relief=tk.FLAT, borderwidth=0, padx=5, pady=3, cursor="hand2",
            font=("Segoe UI", 8, "bold"),
        )
        color_button.pack(side=tk.RIGHT)
        app.body_color_buttons.append(color_button)

        ttk.Label(card, text="PHYSICAL PROPERTIES", style="Section.TLabel").pack(anchor="w", pady=(1, 2))
        mass_radius = ttk.Frame(card, style="Panel.TFrame")
        mass_radius.pack(fill=tk.X, pady=(1, 3))
        mass_group = ttk.Frame(mass_radius, style="Panel.TFrame")
        mass_group.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        ttk.Label(mass_group, text="Mass", style="Panel.TLabel", width=6).pack(side=tk.LEFT)
        mass_entry = ttk.Entry(mass_group, textvariable=var_row[0], width=10)
        mass_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))
        mass_entry.bind("<KeyRelease>", app._on_body_field_edited)
        mass_entry.bind("<<Paste>>", app._on_body_field_edited)

        radius_group = ttk.Frame(mass_radius, style="Panel.TFrame")
        radius_group.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(radius_group, text="Radius", style="Panel.TLabel", width=6).pack(side=tk.LEFT)
        radius_entry = ttk.Entry(radius_group, textvariable=var_row[1], width=10)
        radius_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))
        radius_entry.bind("<KeyRelease>", app._on_body_field_edited)
        radius_entry.bind("<<Paste>>", app._on_body_field_edited)

        ttk.Label(card, text="VISUAL SIZE · display only, never changes the physics",
                  style="Section.TLabel").pack(anchor="w", pady=(4, 1))
        size_row = ttk.Frame(card, style="Panel.TFrame")
        size_row.pack(fill=tk.X)
        size_combo = ttk.Combobox(size_row, textvariable=app.body_size_mode_vars[i], values=SIZE_MODES,
                                  state="readonly", width=12)
        size_combo.pack(side=tk.LEFT)
        size_combo.bind("<<ComboboxSelected>>", lambda _e, idx=i: app._on_body_size_changed(idx))
        size_entry = ttk.Entry(size_row, textvariable=app.body_size_value_vars[i], width=8)
        size_entry.pack(side=tk.LEFT, padx=(6, 6))
        size_entry.bind("<KeyRelease>", lambda _e, idx=i: app._on_body_size_changed(idx))
        size_entry.bind("<<Paste>>", lambda _e, idx=i: app.root.after_idle(app._on_body_size_changed, idx))
        app.body_size_entries.append(size_entry)
        ttk.Label(size_row, textvariable=app.body_size_hint_vars[i], style="Panel.TLabel").pack(side=tk.LEFT)

        ttk.Label(card, text="POSITION · X / Y / Z", style="Section.TLabel").pack(anchor="w", pady=(4, 1))
        position_row = ttk.Frame(card, style="Panel.TFrame")
        position_row.pack(fill=tk.X)
        for j, axis in enumerate(("x", "y", "z")):
            coordinate = ttk.Frame(position_row, style="Panel.TFrame")
            coordinate.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0 if j == 0 else 4, 0))
            ttk.Label(coordinate, text=axis, style="Panel.TLabel").pack(side=tk.LEFT, padx=(0, 3))
            entry = ttk.Entry(coordinate, textvariable=var_row[2+j], width=8)
            entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
            entry.bind("<KeyRelease>", app._on_body_field_edited)
            entry.bind("<<Paste>>", app._on_body_field_edited)

        ttk.Label(card, text="VELOCITY · VX / VY / VZ", style="Section.TLabel").pack(anchor="w", pady=(4, 1))
        velocity_row = ttk.Frame(card, style="Panel.TFrame")
        velocity_row.pack(fill=tk.X)
        for j, axis in enumerate(("vx", "vy", "vz")):
            coordinate = ttk.Frame(velocity_row, style="Panel.TFrame")
            coordinate.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0 if j == 0 else 4, 0))
            ttk.Label(coordinate, text=axis, style="Panel.TLabel").pack(side=tk.LEFT, padx=(0, 3))
            entry = ttk.Entry(coordinate, textvariable=var_row[5+j], width=8)
            entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
            entry.bind("<KeyRelease>", app._on_body_field_edited)
            entry.bind("<<Paste>>", app._on_body_field_edited)

        ttk.Label(card, textvariable=app.metric_vars[i], style=f"Body{i+1}.Panel.TLabel",
                  wraplength=360, justify=tk.LEFT).pack(anchor="w", pady=(5, 0))



def build_settings_panel(app, side) -> None:
    settings = ttk.LabelFrame(side, text="Physics and units", padding=7)
    settings.pack(fill=tk.X, pady=(7, 4))
    app._add_combo_row(settings, 0, "Units", app.units_var, (ARBITRARY, ASTRO), app._unit_changed)
    field_rows = [("Gravitational constant G", app.G_var), ("Time step Δt", app.dt_var),
                  ("Steps per frame", app.steps_var), ("Softening ε (0 = Newtonian)", app.soft_var),
                  ("RK45 relative tolerance", app.rtol_var), ("RK45 absolute tolerance", app.atol_var),
                  ("Shell threshold g*", app.threshold_var), ("View half-width", app.view_var),
                  ("Trail points", app.trail_len_var), ("Bounce restitution", app.restitution_var)]
    row = 1
    for label, var in field_rows:
        ttk.Label(settings, text=label, style="Panel.TLabel", wraplength=150,
                  justify=tk.LEFT).grid(row=row, column=0, sticky="ew", padx=(0, 6), pady=2)
        ent = ttk.Entry(settings, textvariable=var, width=10)
        ent.grid(row=row, column=1, sticky="ew", pady=2)
        ent.bind("<Return>", lambda _e: app._apply_reset())
        row += 1
    app._add_combo_row(settings, row, "Integrator", app.integrator_var, INTEGRATORS); row += 1
    app._add_combo_row(settings, row, "Collision behavior", app.collision_var, COLLISION_MODES); row += 1
    app._add_combo_row(settings, row, "Influence shell", app.zone_mode_var, ZONE_MODES)
    # Reserve enough width for readable labels and let controls shrink gracefully.
    settings.columnconfigure(0, weight=0, minsize=155)
    settings.columnconfigure(1, weight=1, minsize=100)

    display = ttk.LabelFrame(side, text="3D display", padding=7)
    display.pack(fill=tk.X, pady=4)
    for text, var in (("Extra encounter-aware time-step control", app.adaptive_var),
                      ("Auto-fit camera after large excursions", app.autozoom_var),
                      ("Show 3D trajectories", app.trail_var),
                      ("Show floor-projected trails", app.floor_var),
                      ("Show gravitational influence shells", app.shells_var),
                      ("Show coordinate axes", app.axes_var),
                      ("Show combined gravity heatmap", app.field_var),
                      ("Show acceleration vectors", app.accel_var),
                      ("Center initial system on center of mass", app.com_var)):
        ttk.Checkbutton(display, text=text, variable=var, command=app._apply_display_options).pack(anchor="w", pady=1)
    ttk.Label(display, text="Camera view preset", style="Panel.TLabel").pack(anchor="w", pady=(5, 1))
    camera_view_combo = ttk.Combobox(display, textvariable=app.camera_view_preset_var,
                                     values=app.CAMERA_VIEW_PRESETS, state="readonly")
    camera_view_combo.pack(fill=tk.X)
    camera_view_combo.bind("<<ComboboxSelected>>", app._apply_camera_view_preset)
    ttk.Label(display, text="Visualization preset", style="Panel.TLabel").pack(anchor="w", pady=(5, 1))
    visual_preset_combo = ttk.Combobox(display, textvariable=app.visual_preset_var,
                                       values=app.VISUAL_PRESETS, state="readonly")
    visual_preset_combo.pack(fill=tk.X)
    visual_preset_combo.bind("<<ComboboxSelected>>", app._apply_visualization_preset)
    ttk.Label(display, textvariable=app.display_scale_label_var, style="Panel.TLabel").pack(anchor="w", pady=(5, 0))
    ttk.Scale(display, from_=0.5, to=24.0, variable=app.display_scale_var, orient=tk.HORIZONTAL,
              command=app._on_display_scale).pack(fill=tk.X)
    ttk.Label(display, text="Body size preset (sets all three bodies' visual size)",
              style="Panel.TLabel").pack(anchor="w", pady=(6, 0))
    preset_combo = ttk.Combobox(display, textvariable=app.size_preset_var, values=app.SIZE_PRESETS,
                                state="readonly")
    preset_combo.pack(fill=tk.X)
    preset_combo.bind("<<ComboboxSelected>>", lambda _e: app._apply_size_preset())

    actions = ttk.LabelFrame(side, text="Run controls", padding=7)
    actions.pack(fill=tk.X, pady=(6, 4))
    ttk.Button(actions, text="Apply values & reset  (R)", command=app._apply_reset).pack(fill=tk.X, pady=2)
    ttk.Button(actions, text="Play / Pause  (Space)", command=app._toggle_running).pack(fill=tk.X, pady=2)
    row = ttk.Frame(actions, style="Panel.TFrame")
    row.pack(fill=tk.X, pady=2)
    ttk.Button(row, text="Fit view", command=app._fit_camera).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
    ttk.Button(row, text="PNG snapshot…", command=app._save_png).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 0))
    ttk.Button(actions, text="Export history as CSV…", command=app._export_csv).pack(fill=tk.X, pady=2)
    ttk.Button(actions, text="Run physics validation…", command=app._run_validation).pack(fill=tk.X, pady=2)
    ttk.Label(actions, textvariable=app.event_var, style="Panel.TLabel", wraplength=360).pack(anchor="w", pady=(4, 0))
    ttk.Label(side, text="Model note: ε = 0 uses exact Newtonian gravity outside contact; nonzero ε softens the field. Collision events are time-resolved. Influence shells are visualization aids, not gravity boundaries.",
              style="Sub.TLabel", wraplength=360, justify=tk.LEFT).pack(anchor="w", pady=(6, 2))
