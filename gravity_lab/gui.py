"""Tkinter control panel and VTK-embedded interactive 3D visualizer."""
from __future__ import annotations
import csv
import io
import json
import math
import os
import platform
import threading
import time
from datetime import date, datetime, timezone
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import numpy as np
import vtk
import sys
from contextlib import redirect_stdout

from .physics import (ThreeBodyEngine, History, VERLET, YOSHIDA, RK45, INTEGRATORS,
                      MERGE, BOUNCE, PASS, STOP, FRAGMENT, COLLISION_MODES, ZONE_THRESH,
                      ZONE_ROCHE, ZONE_MODES, AU_M, YEAR_S, MSUN_KG, G_AU_MSUN_YR, C_AU_PER_YEAR)
from .presets import PRESETS, PRESET_NAMES, ARBITRARY, ASTRO, engine_inputs
from .renderer_vtk import GravityScene
from .themes import THEMES, BODY_COLORS, BODY_NAMES

BODY_FIELDS = ("Mass", "Radius", "x", "y", "z", "vx", "vy", "vz")
CUSTOM_PRESET = "Custom / Build your own"


def _fmt(value):
    return f"{float(value):.9g}"


def _rgba(hex_color):
    v = hex_color.lstrip("#")
    return tuple(int(v[i:i+2], 16) / 255 for i in (0, 2, 4))


class SparkGraph(tk.Canvas):
    """Lightweight Tk canvas chart; avoids a second live plotting backend."""
    def __init__(self, master, title, colors, **kwargs):
        super().__init__(master, height=148, highlightthickness=1, **kwargs)
        self.title = title
        self.colors = colors
        self.data = []
        self.labels = []
        self.palette = THEMES["Midnight Dark"]

    def set_theme(self, palette):
        self.palette = palette
        self.configure(background=palette["panel_bg"], highlightbackground=palette["border"])
        self.redraw()

    def set_data(self, series, labels=None, logarithmic=False):
        self.data = [np.asarray(list(s), dtype=float) for s in series]
        self.labels = labels or []
        self.logarithmic = logarithmic
        self.redraw()

    def redraw(self):
        self.delete("all")
        w, h = max(self.winfo_width(), 120), max(self.winfo_height(), 80)
        p = self.palette
        self.create_text(10, 8, text=self.title, anchor="nw", fill=p["text"], font=("Segoe UI", 9, "bold"))
        left, right, top, bottom = 38, w - 10, 28, h - 25
        self.create_line(left, top, left, bottom, fill=p["border"])
        self.create_line(left, bottom, right, bottom, fill=p["border"])
        if not self.data or max((len(a) for a in self.data), default=0) < 2:
            self.create_text(w/2, h/2, text="Run the simulation to collect history", fill=p["muted"])
            return
        vals = []
        for a in self.data:
            clean = a[np.isfinite(a)]
            if len(clean):
                if getattr(self, "logarithmic", False):
                    clean = np.log10(np.maximum(clean, 1e-16))
                vals.extend(clean.tolist())
        if not vals:
            return
        ymin, ymax = min(vals), max(vals)
        if abs(ymax - ymin) < 1e-12:
            ymin -= 0.5
            ymax += 0.5
        pad = (ymax - ymin) * 0.08
        ymin, ymax = ymin - pad, ymax + pad
        self.create_text(left - 5, top, text=f"{ymax:.1g}", anchor="e", fill=p["muted"], font=("Segoe UI", 7))
        self.create_text(left - 5, bottom, text=f"{ymin:.1g}", anchor="e", fill=p["muted"], font=("Segoe UI", 7))
        for idx, arr in enumerate(self.data):
            if len(arr) < 2:
                continue
            clean = np.asarray(arr, dtype=float)
            valid = np.isfinite(clean)
            if getattr(self, "logarithmic", False):
                clean = np.log10(np.maximum(clean, 1e-16))
            n = len(clean)
            xs = np.linspace(left, right, n)
            ys = bottom - (clean - ymin) / (ymax - ymin) * (bottom - top)
            coords = []
            for x, y, ok in zip(xs, ys, valid):
                if ok:
                    coords.extend((float(x), float(y)))
                elif len(coords) >= 4:
                    self.create_line(*coords, fill=self.colors[idx % len(self.colors)], width=1.5, smooth=False)
                    coords = []
            if len(coords) >= 4:
                self.create_line(*coords, fill=self.colors[idx % len(self.colors)], width=1.5, smooth=False)
        if self.labels:
            x = left + 4
            for i, label in enumerate(self.labels):
                color = self.colors[i % len(self.colors)]
                self.create_line(x, h-10, x+12, h-10, fill=color, width=2)
                self.create_text(x+16, h-10, text=label, anchor="w", fill=p["muted"], font=("Segoe UI", 7))
                x += 70


class GravityLabApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Gravity Lab 3D | Three-Body Dynamics")
        root.geometry("1650x1000")
        root.minsize(1240, 780)
        self.engine: ThreeBodyEngine | None = None
        self.history = History(maxlen=2200)
        self.running = True
        self.failed = False
        self._dirty = True
        self._frame = 0
        self._last_metric_update = 0
        self._last_event_seen = 0
        self._last_fit_frame = 0
        self._closed = False
        self.system_metadata = {"source": "Built-in preset", "epoch": None, "names": []}
        self.initial_snapshot = None
        self.last_reference_report = ""

        self.theme_var = tk.StringVar(value="Midnight Dark")
        self.view_mode_var = tk.StringVar(value="3D")
        # Optional physics extensions. These are disabled by default so the
        # built-in presets retain their intended Newtonian dynamics.
        self.enable_oblateness_var = tk.BooleanVar(value=False)
        self.enable_1pn_var = tk.BooleanVar(value=False)
        self.enable_tides_var = tk.BooleanVar(value=False)
        self.c_light_var = tk.StringVar(value="1000.0")
        self.tidal_damping_var = tk.StringVar(value="0.05")
        self.j2_vars = [tk.StringVar(value="0.0") for _ in range(3)]
        self.spin_axis_vars = [[tk.StringVar(value=value) for value in ("0", "0", "1")] for _ in range(3)]
        self.spin_omega_vars = [[tk.StringVar(value="0") for _ in range(3)] for _ in range(3)]
        self.preset_var = tk.StringVar(value=PRESET_NAMES[0])
        self.preset_info_var = tk.StringVar(value="")
        self._custom_model_active = False
        self.units_var = tk.StringVar(value=ARBITRARY)
        self.G_var = tk.StringVar(value="1.0")
        self.dt_var = tk.StringVar(value="0.003")
        self.steps_var = tk.StringVar(value="4")
        self.soft_var = tk.StringVar(value="0.0")
        self.rtol_var = tk.StringVar(value="1e-9")
        self.atol_var = tk.StringVar(value="1e-12")
        self.threshold_var = tk.StringVar(value="0.2")
        self.view_var = tk.StringVar(value="12")
        self.trail_len_var = tk.StringVar(value="1200")
        self.restitution_var = tk.StringVar(value="1.0")
        self.integrator_var = tk.StringVar(value=YOSHIDA)
        self.collision_var = tk.StringVar(value=MERGE)
        self.zone_mode_var = tk.StringVar(value=ZONE_THRESH)
        self.adaptive_var = tk.BooleanVar(value=True)
        self.autozoom_var = tk.BooleanVar(value=True)
        self.trail_var = tk.BooleanVar(value=True)
        self.floor_var = tk.BooleanVar(value=True)
        self.shells_var = tk.BooleanVar(value=True)
        self.field_var = tk.BooleanVar(value=True)
        self.accel_var = tk.BooleanVar(value=False)
        self.com_var = tk.BooleanVar(value=True)
        self.speed_var = tk.DoubleVar(value=1.0)
        self.display_scale_var = tk.DoubleVar(value=1.8)
        self.body_vars = [[tk.StringVar(value="0") for _ in BODY_FIELDS] for _ in range(3)]
        self.metric_vars = [tk.StringVar(value="g: — | escape: — | density: —") for _ in range(3)]
        self.status_var = tk.StringVar(value="Starting simulation…")
        self.event_var = tk.StringVar(value="No events yet.")
        self.speed_label_var = tk.StringVar(value="Simulation speed: 1.0×")
        self.display_scale_label_var = tk.StringVar(value="Visual body scale: 1.8×")

        self._configure_style()
        self._build_ui()
        self._load_preset()
        self.root.bind_all("<Key>", self._on_key)
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self._schedule_tick()

    def _configure_style(self):
        self.palette = THEMES.get(self.theme_var.get(), THEMES["Midnight Dark"])
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        p = self.palette
        style.configure("TFrame", background=p["app_bg"])
        style.configure("Panel.TFrame", background=p["panel_bg"])
        style.configure("TLabel", background=p["app_bg"], foreground=p["text"], font=("Segoe UI", 9))
        style.configure("Panel.TLabel", background=p["panel_bg"], foreground=p["text"], font=("Segoe UI", 9))
        style.configure("Title.TLabel", background=p["app_bg"], foreground=p["text"], font=("Segoe UI", 17, "bold"))
        style.configure("Sub.TLabel", background=p["app_bg"], foreground=p["muted"], font=("Segoe UI", 9))
        style.configure("TLabelframe", background=p["panel_bg"], foreground=p["text"], bordercolor=p["border"])
        style.configure("TLabelframe.Label", background=p["panel_bg"], foreground=p["accent"], font=("Segoe UI", 9, "bold"))
        style.configure("TEntry", fieldbackground=p["entry_bg"], foreground=p["text"], insertcolor=p["text"], bordercolor=p["border"])
        style.configure("TCombobox", fieldbackground=p["entry_bg"], background=p["button_bg"], foreground=p["text"], arrowcolor=p["muted"])
        style.map("TCombobox", fieldbackground=[("readonly", p["entry_bg"])], foreground=[("readonly", p["text"])])
        style.configure("TCheckbutton", background=p["panel_bg"], foreground=p["text"])
        style.map("TCheckbutton", background=[("active", p["panel_bg"])], foreground=[("active", p["text"])])
        style.configure("TButton", background=p["button_bg"], foreground=p["text"], borderwidth=0, padding=(8, 6))
        style.map("TButton", background=[("active", p["button_active"]), ("pressed", p["accent"])], foreground=[("disabled", p["muted"])])
        style.configure("Horizontal.TScale", background=p["panel_bg"], troughcolor=p["entry_bg"])
        self.root.configure(bg=p["app_bg"])

    def _build_menu(self):
        """Application menus in the requested File → Settings → Help order."""
        menubar = tk.Menu(self.root)

        files = tk.Menu(menubar, tearoff=False)
        files.add_command(label="Import JPL Horizons states…", command=self._open_horizons_import_dialog)
        files.add_separator()
        files.add_command(label="Load setup from JSON…", command=self._load_setup_json)
        files.add_command(label="Save setup to JSON…", command=self._save_setup_json)
        files.add_separator()
        files.add_command(label="Save current viewport as PNG…", command=self._save_png)
        files.add_command(label="Export simulation history as CSV…", command=self._export_csv)
        files.add_command(label="Save last REBOUND comparison report…", command=self._save_reference_report)

        settings = tk.Menu(menubar, tearoff=False)
        themes = tk.Menu(settings, tearoff=False)
        for theme_name in THEMES:
            themes.add_radiobutton(label=theme_name, variable=self.theme_var, value=theme_name,
                                   command=self._apply_theme)
        settings.add_cascade(label="Theme", menu=themes)
        view_menu = tk.Menu(settings, tearoff=False)
        for mode in ("2D", "3D"):
            view_menu.add_radiobutton(label=f"{mode} view", variable=self.view_mode_var, value=mode,
                                      command=self._apply_view_mode)
        settings.add_cascade(label="Visualizer mode", menu=view_menu)
        settings.add_separator()
        settings.add_command(label="Advanced physics options…", command=self._open_advanced_physics_dialog)
        settings.add_command(label="Apply selected theme", command=self._apply_theme)
        settings.add_command(label="Fit camera to system", command=self._fit_camera)

        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label="Keyboard shortcuts", command=self._show_shortcuts)
        help_menu.add_command(label="Physics model and units", command=self._show_physics_notes)
        help_menu.add_separator()
        help_menu.add_command(label="Run physics validation…", command=self._run_validation)
        help_menu.add_command(label="Compare with REBOUND IAS15…", command=self._open_rebound_comparison_dialog)
        help_menu.add_separator()
        help_menu.add_command(label="About Gravity Lab 3D", command=self._show_about)
        menubar.add_cascade(label="File", menu=files)
        menubar.add_cascade(label="Settings", menu=settings)
        menubar.add_cascade(label="Help", menu=help_menu)
        self.root.configure(menu=menubar)
        self.menubar = menubar

    def _apply_view_mode(self):
        if not hasattr(self, "scene"):
            return
        self.scene.set_view_mode(self.view_mode_var.get())
        if self.engine is not None:
            self.scene.fit_camera(self.engine, view_halfwidth=self._safe_float(self.view_var.get(), self.fixed_view),
                                  include_shells=self.shells_var.get())
        self._dirty = True
        self._render_once(force_field=True)
        self.event_var.set(f"Visualizer switched to {self.view_mode_var.get()} view.")

    def _open_advanced_physics_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Advanced physics models")
        dialog.transient(self.root)
        dialog.geometry("900x730")
        dialog.minsize(820, 650)
        frame = ttk.Frame(dialog, padding=14)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text="ADVANCED PHYSICS", style="Title.TLabel").pack(anchor="w")
        ttk.Label(frame,
                  text="These optional models are approximations. Enable only the effects relevant to your experiment; 1PN and tides require RK45.",
                  style="Sub.TLabel", wraplength=850).pack(anchor="w", pady=(3, 10))

        models = ttk.LabelFrame(frame, text="Global correction models", padding=9)
        models.pack(fill=tk.X, pady=(0, 8))
        ttk.Checkbutton(models, text="J2 oblateness correction (fixed spin axes)",
                        variable=self.enable_oblateness_var).pack(anchor="w", pady=2)
        ttk.Checkbutton(models, text="Pairwise first post-Newtonian correction (1PN)",
                        variable=self.enable_1pn_var).pack(anchor="w", pady=2)
        ttk.Checkbutton(models, text="Phenomenological radial tidal damping / heating proxy",
                        variable=self.enable_tides_var).pack(anchor="w", pady=2)
        row = ttk.Frame(models); row.pack(fill=tk.X, pady=(5, 2))
        ttk.Label(row, text="Speed of light c (model length / model time)").pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=self.c_light_var, width=18).pack(side=tk.RIGHT)
        row = ttk.Frame(models); row.pack(fill=tk.X, pady=(3, 2))
        ttk.Label(row, text="Tidal damping coefficient γ (1 / model time)").pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=self.tidal_damping_var, width=18).pack(side=tk.RIGHT)

        body_box = ttk.LabelFrame(frame, text="Per-body J2, spin axis, and spin angular velocity", padding=9)
        body_box.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        ttk.Label(body_box, text="Spin axes are normalized automatically. Spin ω is in radians per model-time unit; choose aligned vectors for a physically consistent fixed-axis body.",
                  style="Sub.TLabel", wraplength=830).grid(row=0, column=0, columnspan=8, sticky="w", pady=(0, 6))
        headers = ("Body", "J2", "axis x", "axis y", "axis z", "ωx", "ωy", "ωz")
        for col, text in enumerate(headers):
            ttk.Label(body_box, text=text).grid(row=1, column=col, sticky="w", padx=(0, 5))
        for i in range(3):
            ttk.Label(body_box, text=f"Body {i+1}", foreground=BODY_COLORS[i]).grid(row=i+2, column=0, sticky="w", padx=(0, 6), pady=3)
            ttk.Entry(body_box, textvariable=self.j2_vars[i], width=11).grid(row=i+2, column=1, padx=(0, 5), pady=3)
            for j in range(3):
                ttk.Entry(body_box, textvariable=self.spin_axis_vars[i][j], width=9).grid(row=i+2, column=j+2, padx=(0, 5), pady=3)
                ttk.Entry(body_box, textvariable=self.spin_omega_vars[i][j], width=9).grid(row=i+2, column=j+5, padx=(0, 5), pady=3)
        for col in range(8):
            body_box.columnconfigure(col, weight=1)

        notes = ttk.LabelFrame(frame, text="Scientific scope", padding=9)
        notes.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(notes, text=(
            "• Rotational energy and spin angular momentum assume uniform spheres (I = 2/5 MR²); torque-driven spin evolution is not integrated.\n"
            "• J2 models the exterior zonal-harmonic field of an oblate source with a fixed spin axis; spin-axis precession is omitted.\n"
            "• 1PN is a pairwise weak-field approximation, not the full N-body EIH equations; its energy diagnostic omits the 1PN Hamiltonian.\n"
            "• Tidal damping removes relative radial energy and records a heating proxy; it is not a full Love-number or spin-synchronization model.\n"
            "• Fragment mode is a toy two-remnant collision model, not hydrodynamics or material-strength physics."),
            style="Sub.TLabel", justify=tk.LEFT, wraplength=600).pack(anchor="w")
        buttons = ttk.Frame(frame); buttons.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT, padx=(6, 0))
        def apply_advanced():
            try:
                c_value = float(self.c_light_var.get())
                gamma = float(self.tidal_damping_var.get())
                j2_vals = [float(v.get()) for v in self.j2_vars]
                axes = [[float(v.get()) for v in row] for row in self.spin_axis_vars]
                spin_omega = [[float(v.get()) for v in row] for row in self.spin_omega_vars]
                if not math.isfinite(c_value) or c_value <= 0:
                    raise ValueError("c must be finite and positive.")
                if not math.isfinite(gamma) or gamma < 0:
                    raise ValueError("Tidal damping coefficient must be finite and non-negative.")
                if not all(math.isfinite(x) for x in j2_vals + [x for row in axes for x in row] + [x for row in spin_omega for x in row]):
                    raise ValueError("J2, spin-axis and spin angular-velocity entries must be finite.")
                if any(np.linalg.norm(axis) <= 1e-15 for axis in axes):
                    raise ValueError("Every spin-axis direction must be non-zero.")
                if self.enable_tides_var.get() and gamma <= 0:
                    raise ValueError("Enable a positive tidal damping coefficient or turn tides off.")
                if self.enable_1pn_var.get() and c_value <= 0:
                    raise ValueError("1PN requires a positive speed of light in model units.")
                if self.enable_oblateness_var.get() or self.enable_1pn_var.get():
                    if self._safe_float(self.soft_var.get(), 0.0) != 0.0:
                        self.soft_var.set("0")
            except Exception as exc:
                messagebox.showerror("Invalid advanced physics options", str(exc), parent=dialog)
                return
            if self.enable_1pn_var.get() or self.enable_tides_var.get():
                self.integrator_var.set(RK45)
                self.adaptive_var.set(True)
            if self.engine is not None:
                self._apply_reset()
            self.event_var.set("Advanced physics settings applied. Check model-scope notes before interpreting results.")
            dialog.destroy()
        ttk.Button(buttons, text="Apply & reset simulation", command=apply_advanced).pack(side=tk.RIGHT)
        dialog.grab_set()

    def _show_shortcuts(self):
        messagebox.showinfo("Keyboard shortcuts",
            "Space — Play / pause simulation\nR — Apply values and reset (when an entry is not focused)\n"
            "2 — Switch to 2D XY view\n3 — Switch to 3D view\n"
            "Mouse drag — Rotate the 3D camera (3D mode)\nMouse wheel — Zoom\n"
            "Settings → Visualizer mode — Switch between 2D XY and 3D views\n"
            "File — Import JPL Horizons data and save/export results.", parent=self.root)

    def _show_physics_notes(self):
        messagebox.showinfo("Physics model and units",
            "Gravity Lab 3D integrates Newtonian point-mass gravity in 3D. With ε = 0, the inverse-square force is unsoftened outside contact.\n\n"
            "The optional Horizons import uses state vectors in the ecliptic reference plane with the Solar System barycenter as origin, converts AU/day to AU/year, and recentres the selected three-body subsystem. It then evolves only those three bodies, so omitted planets no longer perturb the system.\n\n"
            "Roche-lobe shells are approximate visual guides. Collision responses are simplified rigid-sphere models. J2 is a fixed-axis exterior approximation; 1PN is pairwise, not full EIH; tidal damping is a radial-energy-loss proxy; fragment mode is a two-remnant toy model. These extensions require RK45 for velocity-dependent corrections and must be validated for each experiment.", parent=self.root)

    def _show_about(self):
        messagebox.showinfo("About Gravity Lab 3D",
            "Gravity Lab 3D\nInteractive Newtonian three-body dynamics, collision experiments, field visualization and orbital diagnostics.\n\n"
            "Rendering: VTK · Numerical arrays: NumPy · Interface: Tkinter\nOptional integrations: NASA/JPL Horizons and REBOUND IAS15.", parent=self.root)

    def _save_setup_json(self):
        path = filedialog.asksaveasfilename(parent=self.root, title="Save system setup",
            defaultextension=".json", filetypes=[("Gravity Lab setup", "*.json"), ("JSON", "*.json")])
        if not path:
            return
        string_settings = ("units_var", "G_var", "dt_var", "steps_var", "soft_var", "rtol_var", "atol_var",
                           "threshold_var", "view_var", "trail_len_var", "restitution_var", "integrator_var",
                           "collision_var", "zone_mode_var")
        bool_settings = ("adaptive_var", "autozoom_var", "trail_var", "floor_var", "shells_var", "field_var",
                         "accel_var", "com_var")
        settings = {key.removesuffix("_var"): getattr(self, key).get() for key in string_settings}
        settings.update({key.removesuffix("_var"): bool(getattr(self, key).get()) for key in bool_settings})
        settings.update({"theme": self.theme_var.get(), "speed": float(self.speed_var.get()),
                         "display_scale": float(self.display_scale_var.get()), "view_mode": self.view_mode_var.get(),
                         "enable_oblateness": self.enable_oblateness_var.get(),
                         "enable_1pn": self.enable_1pn_var.get(), "enable_tides": self.enable_tides_var.get(),
                         "c_light": self.c_light_var.get(), "tidal_damping": self.tidal_damping_var.get(),
                         "j2": [v.get() for v in self.j2_vars],
                         "spin_axes": [[v.get() for v in row] for row in self.spin_axis_vars],
                         "spin_omega": [[v.get() for v in row] for row in self.spin_omega_vars]})
        payload = {
            "format": "gravity-lab-3d-setup", "schema_version": 1,
            "preset": self.preset_var.get(),
            "bodies": [[var.get() for var in row] for row in self.body_vars],
            "settings": settings,
            "metadata": self.system_metadata,
            "saved_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            self.event_var.set(f"Saved setup: {os.path.basename(path)}")
        except OSError as exc:
            messagebox.showerror("Save setup failed", str(exc), parent=self.root)

    def _load_setup_json(self):
        path = filedialog.askopenfilename(parent=self.root, title="Load system setup",
            filetypes=[("Gravity Lab setup", "*.json"), ("JSON", "*.json")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            if payload.get("format") != "gravity-lab-3d-setup" or payload.get("schema_version") != 1:
                raise ValueError("This file is not a supported Gravity Lab 3D setup JSON (schema version 1).")
            bodies = payload.get("bodies")
            if not isinstance(bodies, list) or len(bodies) != 3 or any(not isinstance(row, list) or len(row) != len(BODY_FIELDS) for row in bodies):
                raise ValueError("Setup must contain three bodies with mass, radius, position and velocity values.")
            for row_vars, row_values in zip(self.body_vars, bodies):
                for variable, value in zip(row_vars, row_values):
                    variable.set(str(value))
            setting_vars = {
                "units": self.units_var, "G": self.G_var, "dt": self.dt_var, "steps": self.steps_var,
                "soft": self.soft_var, "rtol": self.rtol_var, "atol": self.atol_var,
                "threshold": self.threshold_var, "view": self.view_var, "trail_len": self.trail_len_var,
                "restitution": self.restitution_var, "integrator": self.integrator_var,
                "collision": self.collision_var, "zone_mode": self.zone_mode_var,
            }
            setting_vars.update({"adaptive": self.adaptive_var, "autozoom": self.autozoom_var,
                                 "trail": self.trail_var, "floor": self.floor_var, "shells": self.shells_var,
                                 "field": self.field_var, "accel": self.accel_var, "com": self.com_var})
            settings = payload.get("settings", {})
            for key, variable in setting_vars.items():
                if key in settings:
                    variable.set(settings[key])
            if settings.get("theme") in THEMES:
                self.theme_var.set(settings["theme"])
            if settings.get("view_mode") in ("2D", "3D"):
                self.view_mode_var.set(settings["view_mode"])
            self.enable_oblateness_var.set(bool(settings.get("enable_oblateness", False)))
            self.enable_1pn_var.set(bool(settings.get("enable_1pn", False)))
            self.enable_tides_var.set(bool(settings.get("enable_tides", False)))
            self.c_light_var.set(str(settings.get("c_light", self.c_light_var.get())))
            self.tidal_damping_var.set(str(settings.get("tidal_damping", self.tidal_damping_var.get())))
            for var, value in zip(self.j2_vars, settings.get("j2", ["0", "0", "0"])):
                var.set(str(value))
            for row_vars, values in zip(self.spin_axis_vars, settings.get("spin_axes", [["0", "0", "1"]]*3)):
                for var, value in zip(row_vars, values): var.set(str(value))
            for row_vars, values in zip(self.spin_omega_vars, settings.get("spin_omega", [["0", "0", "0"]]*3)):
                for var, value in zip(row_vars, values): var.set(str(value))
            if "speed" in settings:
                self.speed_var.set(float(settings["speed"]))
            if "display_scale" in settings:
                self.display_scale_var.set(float(settings["display_scale"]))
            preset = payload.get("preset", CUSTOM_PRESET)
            if preset in PRESETS:
                self.preset_var.set(preset)
                self._custom_model_active = False
            else:
                self.preset_var.set(CUSTOM_PRESET)
                self._custom_model_active = True
                self.preset_info_var.set(
                    "Custom setup loaded. Edit body mass, radius, position and velocity, "
                    "then click Apply values & reset."
                )
            self.system_metadata = payload.get("metadata", {"source": "Loaded setup JSON", "names": []})
            self._configure_style()
            self.apply_theme_widgets()
            self._apply_reset()
            self.event_var.set(f"Loaded setup: {os.path.basename(path)}")
        except Exception as exc:
            messagebox.showerror("Load setup failed", str(exc), parent=self.root)

    def _open_horizons_import_dialog(self):
        from .ephemeris import SOLAR_SYSTEM_BODIES
        dialog = tk.Toplevel(self.root)
        dialog.title("Import NASA/JPL Horizons state vectors")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        frame = ttk.Frame(dialog, padding=14)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text="Import a real Solar System state at one epoch", style="Title.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(frame, text="Vectors use the SSB origin, ecliptic plane, AU and AU/day; velocities are converted to AU/year.",
                  wraplength=470, style="Sub.TLabel").grid(row=1, column=0, columnspan=2, sticky="w", pady=(5, 10))
        epoch_var = tk.StringVar(value=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
        ttk.Label(frame, text="Epoch in TDB (date or date + HH:MM)").grid(row=2, column=0, sticky="w", padx=(0, 10))
        ttk.Entry(frame, textvariable=epoch_var, width=24).grid(row=2, column=1, sticky="ew", pady=3)
        choices = list(SOLAR_SYSTEM_BODIES)
        defaults = ("Sun", "Earth", "Jupiter")
        body_vars = []
        for i in range(3):
            var = tk.StringVar(value=defaults[i])
            body_vars.append(var)
            ttk.Label(frame, text=f"Body {i+1}").grid(row=3+i, column=0, sticky="w", padx=(0, 10))
            ttk.Combobox(frame, textvariable=var, values=choices, state="readonly", width=22).grid(row=3+i, column=1, sticky="ew", pady=3)
        status = tk.StringVar(value="Requires an internet connection to query JPL Horizons.")
        ttk.Label(frame, textvariable=status, wraplength=470).grid(row=6, column=0, columnspan=2, sticky="w", pady=(8, 8))
        buttons = ttk.Frame(frame)
        buttons.grid(row=7, column=0, columnspan=2, sticky="ew")
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT, padx=(6, 0))
        fetch_button = ttk.Button(buttons, text="Fetch and apply", command=lambda: start_fetch())
        fetch_button.pack(side=tk.RIGHT)
        frame.columnconfigure(1, weight=1)

        def start_fetch():
            names = tuple(v.get() for v in body_vars)
            epoch = epoch_var.get().strip()
            if len(set(names)) != 3:
                messagebox.showerror("Choose three different bodies", "Each of the three selected bodies must be different.", parent=dialog)
                return
            fetch_button.configure(state=tk.DISABLED)
            status.set("Contacting JPL Horizons… this can take a few seconds.")
            def worker():
                try:
                    from .ephemeris import fetch_three_body_horizons
                    result = fetch_three_body_horizons(names, epoch)
                    self.root.after(0, lambda result=result: self._apply_horizons_import(result, dialog))
                except Exception as exc:
                    error = str(exc)
                    self.root.after(0, lambda error=error: failed(error))
            def failed(error):
                if dialog.winfo_exists():
                    status.set(f"Import failed: {error}")
                    fetch_button.configure(state=tk.NORMAL)
            threading.Thread(target=worker, daemon=True, name="HorizonsImport").start()
        dialog.bind("<Return>", lambda _e: start_fetch())
        dialog.grab_set()
        dialog.focus_set()

    def _apply_horizons_import(self, result, dialog=None):
        # If the user cancelled/closed the import dialog while the request was in
        # flight, ignore the completed response rather than silently replacing the system.
        if dialog is not None:
            try:
                if not dialog.winfo_exists():
                    return
            except tk.TclError:
                return
        self.units_var.set(ASTRO)
        self.G_var.set(_fmt(result.gravitational_constant))
        self.c_light_var.set(_fmt(C_AU_PER_YEAR))
        self.soft_var.set("0")
        self.collision_var.set(PASS)
        self.integrator_var.set(RK45)
        self.enable_oblateness_var.set(False)
        self.enable_1pn_var.set(False)
        self.enable_tides_var.set(False)
        for var in self.j2_vars: var.set("0")
        for row in self.spin_axis_vars:
            for var, value in zip(row, ("0", "0", "1")): var.set(value)
        for row in self.spin_omega_vars:
            for var in row: var.set("0")
        self.rtol_var.set("1e-10")
        self.atol_var.set("1e-13")
        self.adaptive_var.set(True)
        self.com_var.set(True)
        self.dt_var.set("0.001")
        self.steps_var.set("10")
        self.threshold_var.set("10")
        extent = max(float(np.max(np.abs(result.positions))), 1.0)
        self.view_var.set(_fmt(extent * 1.3))
        for i in range(3):
            vals = [result.masses[i], result.radii[i], *result.positions[i], *result.velocities[i]]
            for variable, value in zip(self.body_vars[i], vals):
                variable.set(_fmt(value))
        self.preset_var.set("Custom / JPL Horizons")
        self.system_metadata = {
            "source": result.source, "epoch": result.epoch, "names": list(result.names),
            "reference_frame": result.reference_frame,
            "note": "Initial states imported from JPL Horizons; subsequent motion evolves only the selected three-body subsystem.",
        }
        self._apply_reset()
        self.event_var.set(f"Imported JPL Horizons: {', '.join(result.names)} at {result.epoch}")
        if dialog is not None:
            try:
                dialog.grab_release()
                dialog.destroy()
            except tk.TclError:
                pass
        messagebox.showinfo("Horizons import complete",
            f"Imported {', '.join(result.names)} at {result.epoch}.\n\n"
            "Initial vectors were fetched relative to the Solar System barycenter, converted to AU/year, and shifted to the selected trio's center-of-mass frame. The later simulation includes only these three bodies, so other planets will not continue to perturb them.", parent=self.root)

    def _open_rebound_comparison_dialog(self):
        if self.initial_snapshot is None:
            messagebox.showwarning("No initial state", "Apply or reset a system before comparison.", parent=self.root)
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("Compare with REBOUND IAS15")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        frame = ttk.Frame(dialog, padding=14)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text="Independent N-body reference comparison", style="Title.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(frame, text="Integrates the saved initial state using your RK45 engine and REBOUND's IAS15 integrator. Requires ε = 0 and an installed optional REBOUND package.",
                  wraplength=480, style="Sub.TLabel").grid(row=1, column=0, columnspan=2, sticky="w", pady=(5, 10))
        duration_default = "1.0" if self.units_var.get() == ASTRO else "2.0"
        duration_var = tk.StringVar(value=duration_default)
        samples_var = tk.StringVar(value="120")
        ttk.Label(frame, text="Duration (current simulation time units)").grid(row=2, column=0, sticky="w", padx=(0, 12))
        ttk.Entry(frame, textvariable=duration_var, width=14).grid(row=2, column=1, sticky="ew", pady=3)
        ttk.Label(frame, text="Comparison sample count (2–5000)").grid(row=3, column=0, sticky="w", padx=(0, 12))
        ttk.Entry(frame, textvariable=samples_var, width=14).grid(row=3, column=1, sticky="ew", pady=3)
        status = tk.StringVar(value="The comparison runs in a background thread.")
        ttk.Label(frame, textvariable=status, wraplength=480).grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 8))
        buttons = ttk.Frame(frame); buttons.grid(row=5, column=0, columnspan=2, sticky="e")
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT, padx=(6, 0))
        run_btn = ttk.Button(buttons, text="Run comparison", command=lambda: run_compare())
        run_btn.pack(side=tk.RIGHT)
        frame.columnconfigure(1, weight=1)

        def run_compare():
            try:
                duration = float(duration_var.get())
                samples = int(samples_var.get())
                if not math.isfinite(duration) or duration <= 0 or not 2 <= samples <= 5000:
                    raise ValueError("Use a positive finite duration and 2–5000 samples.")
                snap = self.initial_snapshot
                if snap["softening"] != 0:
                    raise ValueError("REBOUND comparison requires ε = 0. Set softening to zero and reset first.")
                if snap.get("enable_oblateness", False) or snap.get("enable_1pn", False) or snap.get("tidal_damping", 0.0) > 0:
                    raise ValueError("The current REBOUND comparison backend validates the isolated Newtonian point-mass model. Turn off J2, 1PN, and tidal corrections first.")
                if any(np.linalg.norm(snap["pos"][j]-snap["pos"][i]) <= snap["R"][i]+snap["R"][j]
                       for i, j in ((0, 1), (0, 2), (1, 2))):
                    raise ValueError("The initial bodies overlap. Separate them before comparing point-mass trajectories.")
            except Exception as exc:
                messagebox.showerror("Invalid comparison setup", str(exc), parent=dialog)
                return
            snapshot = {key: (value.copy() if isinstance(value, np.ndarray) else value) for key, value in snap.items()}
            run_btn.configure(state=tk.DISABLED)
            status.set("Running RK45 vs REBOUND IAS15…")
            def worker():
                try:
                    from .rebound_compare import compare_against_rebound
                    result = compare_against_rebound(snapshot["m"], snapshot["R"], snapshot["pos"], snapshot["vel"],
                        snapshot["G"], duration, samples, snapshot["softening"], snapshot["rtol"], snapshot["atol"])
                    report = ("REBOUND IAS15 vs Gravity Lab RK45\n"
                        f"Duration: {result.duration:.8g}\nSamples: {result.samples}\n"
                        f"Characteristic initial separation: {result.characteristic_separation:.8e}\n"
                        f"RMS position difference: {result.rms_position_error:.8e}\n"
                        f"Maximum position difference: {result.max_position_error:.8e}\n"
                        f"Relative RMS difference: {result.relative_rms_error:.8e}\n"
                        f"Relative maximum difference: {result.relative_max_error:.8e}\n\n"
                        "This compares two numerical integrators for the same isolated, unsoftened point-mass model. It is not a comparison with real ephemerides.")
                    self.root.after(0, lambda report=report: comparison_done(report))
                except Exception as exc:
                    error = str(exc)
                    self.root.after(0, lambda error=error: comparison_failed(error))
            def comparison_done(report):
                if dialog.winfo_exists():
                    self.last_reference_report = report
                    status.set("Comparison completed.")
                    run_btn.configure(state=tk.NORMAL)
                    messagebox.showinfo("REBOUND comparison result", report, parent=dialog)
            def comparison_failed(error):
                if dialog.winfo_exists():
                    status.set(f"Comparison failed: {error}")
                    run_btn.configure(state=tk.NORMAL)
                    messagebox.showerror("REBOUND comparison failed", error, parent=dialog)
            threading.Thread(target=worker, daemon=True, name="ReboundComparison").start()
        dialog.bind("<Return>", lambda _e: run_compare())
        dialog.grab_set()

    def _save_reference_report(self):
        if not self.last_reference_report:
            messagebox.showinfo("No REBOUND report", "Run a REBOUND comparison first.", parent=self.root)
            return
        path = filedialog.asksaveasfilename(parent=self.root, title="Save comparison report",
            defaultextension=".txt", filetypes=[("Text file", "*.txt")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.last_reference_report)
            self.event_var.set(f"Saved reference report: {os.path.basename(path)}")
        except OSError as exc:
            messagebox.showerror("Save report failed", str(exc), parent=self.root)

    def _build_ui(self):
        self._build_menu()
        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill=tk.BOTH, expand=True)
        header = ttk.Frame(outer)
        header.pack(fill=tk.X, pady=(0, 9))
        ttk.Label(header, text="GRAVITY LAB 3D", style="Title.TLabel").pack(side=tk.LEFT)
        ttk.Label(header, text="Newtonian three-body dynamics  ·  advanced corrections  ·  orbital diagnostics",
                  style="Sub.TLabel").pack(side=tk.LEFT, padx=(16, 0), pady=(6, 0))
        toolbar = ttk.Frame(outer, style="Panel.TFrame", padding=(8, 5))
        toolbar.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(toolbar, text="Visualizer:", style="Panel.TLabel").pack(side=tk.LEFT, padx=(0, 5))
        view_combo = ttk.Combobox(toolbar, textvariable=self.view_mode_var, values=("2D", "3D"),
                                  state="readonly", width=7)
        view_combo.pack(side=tk.LEFT, padx=(0, 10))
        view_combo.bind("<<ComboboxSelected>>", lambda _e: self._apply_view_mode())
        ttk.Button(toolbar, text="Advanced physics…", command=self._open_advanced_physics_dialog).pack(side=tk.LEFT, padx=3)
        ttk.Button(toolbar, text="Pause / Play", command=self._toggle_running).pack(side=tk.LEFT, padx=3)
        ttk.Button(toolbar, text="Reset", command=self._apply_reset).pack(side=tk.LEFT, padx=3)
        content = ttk.Frame(outer)
        content.pack(fill=tk.BOTH, expand=True)
        side_shell = ttk.Frame(content, width=420)
        side_shell.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        side_shell.pack_propagate(False)
        self.side_canvas = tk.Canvas(side_shell, bg=self.palette["app_bg"], highlightthickness=0, width=412)
        scroll = ttk.Scrollbar(side_shell, orient=tk.VERTICAL, command=self.side_canvas.yview)
        self.side_canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.side_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.side_inner = ttk.Frame(self.side_canvas, style="Panel.TFrame", padding=10)
        self.side_window = self.side_canvas.create_window((0, 0), window=self.side_inner, anchor="nw")
        self.side_inner.bind("<Configure>", lambda _e: self.side_canvas.configure(scrollregion=self.side_canvas.bbox("all")))
        self.side_canvas.bind("<Configure>", lambda e: self.side_canvas.itemconfigure(self.side_window, width=e.width))
        self.side_canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self._build_sidebar()

        main = ttk.Frame(content, style="Panel.TFrame", padding=5)
        main.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        # Embed a native VTK OpenGL window directly into a Tk canvas. This avoids
        # requiring the optional libvtkRenderingTk bridge that many VTK wheels omit.
        self.vtk_canvas = tk.Canvas(main, bg=self.palette["plot_bg"], highlightthickness=0, takefocus=1)
        self.vtk_canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.vtk_canvas.update_idletasks()
        self.vtk_render_window = self._new_native_render_window()
        # IMPORTANT: Tk owns the Canvas window. VTK must create its drawable as
        # a CHILD of that Canvas, not treat the Canvas handle as a complete
        # pre-existing VTK window. SetParentInfo() is the embedding API. VTK's
        # native implementations parse this string as a decimal integer, so do
        # not use hex(parent_handle): the parse failure silently leaves ParentId
        # unset and creates a separate top-level VTK window.
        parent_handle = self.vtk_canvas.winfo_id()
        if not hasattr(self.vtk_render_window, "SetParentInfo"):
            raise RuntimeError(
                "This VTK render-window backend does not expose SetParentInfo(), "
                "which is required to embed the 3D viewport in the main window. "
                "Please install a standard VTK 9.x wheel."
            )
        self.vtk_render_window.SetParentInfo(str(parent_handle))
        self.vtk_render_window.SetSize(max(320, self.vtk_canvas.winfo_width()), max(240, self.vtk_canvas.winfo_height()))
        self.scene = GravityScene(self.vtk_render_window, theme=self.theme_var.get(), grid_size=53)
        self.vtk_interactor = vtk.vtkRenderWindowInteractor()
        self.vtk_interactor.SetRenderWindow(self.vtk_render_window)
        self.vtk_interactor.SetInteractorStyle(vtk.vtkInteractorStyleTrackballCamera())
        self.vtk_interactor.Initialize()
        self._bind_vtk_mouse_events()
        self.vtk_canvas.bind("<Configure>", self._resize_vtk)
        self.vtk_canvas.bind("<Expose>", lambda _e: self.root.after_idle(self._render_once))
        self.graph_frame = ttk.Frame(main, style="Panel.TFrame")
        self.graph_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(5, 0))
        self.separation_graph = SparkGraph(self.graph_frame, "PAIR SEPARATIONS", ("#9fb3c8", "#f6bd60", "#84a59d"))
        self.separation_graph.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 3))
        self.energy_graph = SparkGraph(self.graph_frame, "ENERGY DRIFT |log10|", ("#c77dff",))
        self.energy_graph.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(3, 0))
        self.status = ttk.Label(main, textvariable=self.status_var, style="Panel.TLabel", anchor="w")
        self.status.pack(side=tk.BOTTOM, fill=tk.X, pady=(4, 0))
        self.apply_theme_widgets()

    def _new_native_render_window(self):
        """Select an OS-native render window so its drawable can live in a Tk canvas."""
        if sys.platform.startswith("win") and hasattr(vtk, "vtkWin32OpenGLRenderWindow"):
            return vtk.vtkWin32OpenGLRenderWindow()
        if sys.platform == "darwin" and hasattr(vtk, "vtkCocoaRenderWindow"):
            return vtk.vtkCocoaRenderWindow()
        if hasattr(vtk, "vtkXOpenGLRenderWindow"):
            return vtk.vtkXOpenGLRenderWindow()
        # Last-resort backend; SetWindowInfo might not support embedding on this build.
        return vtk.vtkRenderWindow()

    def _bind_vtk_mouse_events(self):
        self.vtk_canvas.bind("<ButtonPress-1>", lambda e: self._vtk_mouse(e, "LeftButtonPressEvent"))
        self.vtk_canvas.bind("<ButtonRelease-1>", lambda e: self._vtk_mouse(e, "LeftButtonReleaseEvent"))
        self.vtk_canvas.bind("<ButtonPress-2>", lambda e: self._vtk_mouse(e, "MiddleButtonPressEvent"))
        self.vtk_canvas.bind("<ButtonRelease-2>", lambda e: self._vtk_mouse(e, "MiddleButtonReleaseEvent"))
        self.vtk_canvas.bind("<ButtonPress-3>", lambda e: self._vtk_mouse(e, "RightButtonPressEvent"))
        self.vtk_canvas.bind("<ButtonRelease-3>", lambda e: self._vtk_mouse(e, "RightButtonReleaseEvent"))
        self.vtk_canvas.bind("<B1-Motion>", lambda e: self._vtk_mouse(e, "MouseMoveEvent"))
        self.vtk_canvas.bind("<B2-Motion>", lambda e: self._vtk_mouse(e, "MouseMoveEvent"))
        self.vtk_canvas.bind("<B3-Motion>", lambda e: self._vtk_mouse(e, "MouseMoveEvent"))
        self.vtk_canvas.bind("<Motion>", lambda e: self._vtk_mouse(e, "MouseMoveEvent"))
        self.vtk_canvas.bind("<MouseWheel>", self._vtk_wheel)
        self.vtk_canvas.bind("<Button-4>", lambda e: self._vtk_mouse(e, "MouseWheelForwardEvent"))
        self.vtk_canvas.bind("<Button-5>", lambda e: self._vtk_mouse(e, "MouseWheelBackwardEvent"))

    def _vtk_mouse(self, event, vtk_event):
        try:
            self.vtk_canvas.focus_set()
            height = max(1, self.vtk_canvas.winfo_height())
            self.vtk_interactor.SetEventPosition(int(event.x), int(height - event.y))
            getattr(self.vtk_interactor, vtk_event)()
        except (AttributeError, RuntimeError):
            pass

    def _vtk_wheel(self, event):
        self._vtk_mouse(event, "MouseWheelForwardEvent" if event.delta > 0 else "MouseWheelBackwardEvent")

    def _resize_vtk(self, event=None):
        if not hasattr(self, "vtk_render_window"):
            return
        try:
            w = max(320, self.vtk_canvas.winfo_width())
            h = max(240, self.vtk_canvas.winfo_height())
            self.vtk_render_window.SetSize(w, h)
            self._dirty = True
            if not self.running:
                self.root.after_idle(self._render_once)
        except Exception:
            pass

    def _build_sidebar(self):
        side = self.side_inner
        ttk.Label(side, text="SIMULATION SETUP", style="Panel.TLabel", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        ttk.Label(side, text="Edit the bodies, then apply and reset. Drag to rotate; scroll to zoom.",
                  style="Panel.TLabel", wraplength=360).pack(anchor="w", pady=(2, 8))

        preset_box = ttk.LabelFrame(side, text="Starting system", padding=7)
        preset_box.pack(fill=tk.X, pady=(0, 7))
        self.preset_combo = ttk.Combobox(
            preset_box,
            textvariable=self.preset_var,
            values=[CUSTOM_PRESET, *PRESET_NAMES],
            state="readonly",
        )
        self.preset_combo.pack(fill=tk.X)
        self.preset_combo.bind("<<ComboboxSelected>>", self._on_preset_selected)
        ttk.Button(
            preset_box,
            text="＋ Build a new custom model",
            command=self._start_custom_model,
        ).pack(fill=tk.X, pady=(5, 0))
        ttk.Label(preset_box, textvariable=self.preset_info_var, style="Sub.TLabel",
                  wraplength=365, justify=tk.LEFT).pack(anchor="w", pady=(5, 0))

        for i, var_row in enumerate(self.body_vars):
            card = ttk.LabelFrame(side, text=f"BODY {i + 1}  ·  {BODY_NAMES[i]}", padding=7)
            card.pack(fill=tk.X, pady=4)
            ttk.Label(card, text="Mass", style="Panel.TLabel").grid(row=0, column=0, sticky="w")
            mass_entry = ttk.Entry(card, textvariable=var_row[0], width=11)
            mass_entry.grid(row=0, column=1, sticky="ew", padx=(4, 7), pady=2)
            mass_entry.bind("<KeyRelease>", self._on_body_field_edited)
            mass_entry.bind("<<Paste>>", self._on_body_field_edited)
            ttk.Label(card, text="Radius", style="Panel.TLabel").grid(row=0, column=2, sticky="w")
            radius_entry = ttk.Entry(card, textvariable=var_row[1], width=11)
            radius_entry.grid(row=0, column=3, sticky="ew", padx=(4, 0), pady=2)
            radius_entry.bind("<KeyRelease>", self._on_body_field_edited)
            radius_entry.bind("<<Paste>>", self._on_body_field_edited)
            ttk.Label(card, text="Position (x, y, z)", style="Panel.TLabel").grid(row=1, column=0, columnspan=4, sticky="w", pady=(4, 0))
            for j, axis in enumerate(("x", "y", "z")):
                ttk.Label(card, text=axis, style="Panel.TLabel").grid(row=2, column=j*2, sticky="e", padx=(0, 3))
                entry = ttk.Entry(card, textvariable=var_row[2+j], width=9)
                entry.grid(row=2, column=j*2+1, sticky="ew", padx=(0, 3), pady=2)
                entry.bind("<KeyRelease>", self._on_body_field_edited)
                entry.bind("<<Paste>>", self._on_body_field_edited)
            ttk.Label(card, text="Velocity (vx, vy, vz)", style="Panel.TLabel").grid(row=3, column=0, columnspan=4, sticky="w", pady=(4, 0))
            for j, axis in enumerate(("vx", "vy", "vz")):
                ttk.Label(card, text=axis, style="Panel.TLabel").grid(row=4, column=j*2, sticky="e", padx=(0, 3))
                entry = ttk.Entry(card, textvariable=var_row[5+j], width=9)
                entry.grid(row=4, column=j*2+1, sticky="ew", padx=(0, 3), pady=2)
                entry.bind("<KeyRelease>", self._on_body_field_edited)
                entry.bind("<<Paste>>", self._on_body_field_edited)
            for c in range(4):
                card.columnconfigure(c, weight=1)
            ttk.Label(card, textvariable=self.metric_vars[i], style="Panel.TLabel", wraplength=360,
                      foreground=BODY_COLORS[i]).grid(row=5, column=0, columnspan=4, sticky="w", pady=(5, 0))

        settings = ttk.LabelFrame(side, text="Physics and units", padding=7)
        settings.pack(fill=tk.X, pady=(7, 4))
        self._add_combo_row(settings, 0, "Units", self.units_var, (ARBITRARY, ASTRO), self._unit_changed)
        field_rows = [("Gravitational constant G", self.G_var), ("Time step Δt", self.dt_var),
                      ("Steps per frame", self.steps_var), ("Softening ε (0 = Newtonian)", self.soft_var),
                      ("RK45 relative tolerance", self.rtol_var), ("RK45 absolute tolerance", self.atol_var),
                      ("Shell threshold g*", self.threshold_var), ("View half-width", self.view_var),
                      ("Trail points", self.trail_len_var), ("Bounce restitution", self.restitution_var)]
        row = 1
        for label, var in field_rows:
            ttk.Label(settings, text=label, style="Panel.TLabel").grid(row=row, column=0, sticky="w", padx=(0, 6), pady=2)
            ent = ttk.Entry(settings, textvariable=var, width=13)
            ent.grid(row=row, column=1, sticky="e", pady=2)
            ent.bind("<Return>", lambda _e: self._apply_reset())
            row += 1
        self._add_combo_row(settings, row, "Integrator", self.integrator_var, INTEGRATORS); row += 1
        self._add_combo_row(settings, row, "Collision behavior", self.collision_var, COLLISION_MODES); row += 1
        self._add_combo_row(settings, row, "Influence shell", self.zone_mode_var, ZONE_MODES)
        settings.columnconfigure(0, weight=1)

        display = ttk.LabelFrame(side, text="3D display", padding=7)
        display.pack(fill=tk.X, pady=4)
        for text, var in (("Extra encounter-aware time-step control", self.adaptive_var),
                          ("Auto-fit camera after large excursions", self.autozoom_var),
                          ("Show 3D trajectories", self.trail_var),
                          ("Show floor-projected trails", self.floor_var),
                          ("Show gravitational influence shells", self.shells_var),
                          ("Show combined gravity heatmap", self.field_var),
                          ("Show acceleration vectors", self.accel_var),
                          ("Center initial system on center of mass", self.com_var)):
            ttk.Checkbutton(display, text=text, variable=var, command=self._apply_display_options).pack(anchor="w", pady=1)
        ttk.Label(display, textvariable=self.display_scale_label_var, style="Panel.TLabel").pack(anchor="w", pady=(5, 0))
        ttk.Scale(display, from_=0.5, to=24.0, variable=self.display_scale_var, orient=tk.HORIZONTAL,
                  command=self._on_display_scale).pack(fill=tk.X)
        ttk.Label(display, textvariable=self.speed_label_var, style="Panel.TLabel").pack(anchor="w", pady=(4, 0))
        ttk.Scale(display, from_=0.1, to=5.0, variable=self.speed_var, orient=tk.HORIZONTAL,
                  command=self._on_speed).pack(fill=tk.X)

        actions = ttk.LabelFrame(side, text="Run controls", padding=7)
        actions.pack(fill=tk.X, pady=(6, 4))
        ttk.Button(actions, text="Apply values & reset  (R)", command=self._apply_reset).pack(fill=tk.X, pady=2)
        ttk.Button(actions, text="Play / Pause  (Space)", command=self._toggle_running).pack(fill=tk.X, pady=2)
        row = ttk.Frame(actions, style="Panel.TFrame")
        row.pack(fill=tk.X, pady=2)
        ttk.Button(row, text="Fit camera", command=self._fit_camera).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
        ttk.Button(row, text="PNG snapshot…", command=self._save_png).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 0))
        ttk.Button(actions, text="Export history as CSV…", command=self._export_csv).pack(fill=tk.X, pady=2)
        ttk.Button(actions, text="Run physics validation…", command=self._run_validation).pack(fill=tk.X, pady=2)
        ttk.Label(actions, textvariable=self.event_var, style="Panel.TLabel", wraplength=360).pack(anchor="w", pady=(4, 0))
        ttk.Label(side, text="Model note: ε = 0 uses exact Newtonian gravity outside contact; nonzero ε softens the field. Collision events are time-resolved. Influence shells are visualization aids, not gravity boundaries.",
                  style="Sub.TLabel", wraplength=360, justify=tk.LEFT).pack(anchor="w", pady=(6, 2))

    @staticmethod
    def _add_combo_row(parent, row, label, variable, values, callback=None):
        ttk.Label(parent, text=label, style="Panel.TLabel").grid(row=row, column=0, sticky="w", padx=(0, 6), pady=2)
        combo = ttk.Combobox(parent, textvariable=variable, values=values, state="readonly", width=26)
        combo.grid(row=row, column=1, sticky="ew", pady=2)
        if callback:
            combo.bind("<<ComboboxSelected>>", lambda _e: callback())
        return combo

    def apply_theme_widgets(self):
        self.palette = THEMES.get(self.theme_var.get(), THEMES["Midnight Dark"])
        p = self.palette
        self.root.configure(bg=p["app_bg"])
        self.side_canvas.configure(bg=p["app_bg"])
        self.separation_graph.set_theme(p)
        self.energy_graph.set_theme(p)
        if hasattr(self, "scene"):
            self.scene.set_theme(self.theme_var.get())
            self._dirty = True

    def _apply_theme(self):
        self._configure_style()
        self.apply_theme_widgets()
        self._render_once(force_field=True)

    def _on_mousewheel(self, event):
        try:
            if self.side_canvas.winfo_containing(event.x_root, event.y_root) is not None:
                self.side_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except (tk.TclError, AttributeError):
            pass

    def _unit_changed(self):
        self.G_var.set(_fmt(G_AU_MSUN_YR if self.units_var.get() == ASTRO else 1.0))
        self.c_light_var.set(_fmt(C_AU_PER_YEAR if self.units_var.get() == ASTRO else 1000.0))

    def _on_speed(self, value):
        self.speed_label_var.set(f"Simulation speed: {float(value):.1f}×")

    def _on_display_scale(self, value):
        self.display_scale_label_var.set(f"Visual body scale: {float(value):.1f}× (visual only)")
        self._apply_display_options()

    def _apply_display_options(self):
        if not hasattr(self, "scene"):
            return
        self.scene.set_display_options(
            display_scale=self.display_scale_var.get(), show_shells=self.shells_var.get(),
            show_field=self.field_var.get(), show_trails=self.trail_var.get(),
            show_floor=self.floor_var.get(), show_acceleration=self.accel_var.get(),
            zone_mode=self.zone_mode_var.get(), threshold=self._safe_float(self.threshold_var.get(), 0.2))
        self._dirty = True
        if not self.running:
            self._render_once(force_field=True)

    @staticmethod
    def _safe_float(text, default=0.0):
        try:
            v = float(text)
            return v if math.isfinite(v) else default
        except (ValueError, TypeError):
            return default

    def _read_inputs(self):
        parsed = []
        for i, row in enumerate(self.body_vars, start=1):
            vals = []
            for name, var in zip(BODY_FIELDS, row):
                raw = var.get().strip()
                try:
                    value = float(raw)
                except ValueError:
                    raise ValueError(f"Body {i} {name}: '{raw}' is not a number.")
                if not math.isfinite(value):
                    raise ValueError(f"Body {i} {name} must be finite.")
                vals.append(value)
            if vals[0] <= 0 or vals[1] <= 0:
                raise ValueError(f"Body {i}: mass and radius must be greater than zero.")
            parsed.append(vals)
        p = np.asarray(parsed, dtype=float)
        try:
            G = float(self.G_var.get()); dt = float(self.dt_var.get()); steps = int(self.steps_var.get())
            soft = float(self.soft_var.get()); threshold = float(self.threshold_var.get())
            rtol = float(self.rtol_var.get()); atol = float(self.atol_var.get())
            view = float(self.view_var.get()); trails = int(self.trail_len_var.get())
            restitution = float(self.restitution_var.get())
        except ValueError:
            raise ValueError("G, Δt, steps, softening, threshold, view, trails and restitution must be valid numbers.")
        if not all(math.isfinite(v) for v in (G, dt, soft, threshold, view, restitution, rtol, atol)):
            raise ValueError("Simulation parameters and RK45 tolerances must be finite.")
        if G < 0 or dt <= 0 or not 1 <= steps <= 1000 or soft < 0 or threshold <= 0 or view <= 0 or trails < 10:
            raise ValueError("Require G ≥ 0, Δt > 0, 1 ≤ steps ≤ 1000, softening ≥ 0, threshold/view > 0 and trails ≥ 10.")
        if not 0 < rtol < 1 or atol <= 0:
            raise ValueError("RK45 tolerances must satisfy 0 < relative tolerance < 1 and absolute tolerance > 0.")
        if not 0 <= restitution <= 1:
            raise ValueError("Bounce restitution must be between 0 and 1.")
        try:
            c_light = float(self.c_light_var.get())
            tidal_damping = float(self.tidal_damping_var.get())
            j2 = np.asarray([float(v.get()) for v in self.j2_vars], dtype=float)
            spin_axes = np.asarray([[float(v.get()) for v in row] for row in self.spin_axis_vars], dtype=float)
            spin_omega = np.asarray([[float(v.get()) for v in row] for row in self.spin_omega_vars], dtype=float)
        except ValueError:
            raise ValueError("Advanced physics parameters must be valid numbers.")
        if not math.isfinite(c_light) or c_light <= 0 or not math.isfinite(tidal_damping) or tidal_damping < 0:
            raise ValueError("c must be positive and tidal damping must be non-negative.")
        if (not np.all(np.isfinite(j2)) or not np.all(np.isfinite(spin_axes)) or not np.all(np.isfinite(spin_omega))
                or np.any(np.linalg.norm(spin_axes, axis=1) <= 1e-15)):
            raise ValueError("J2, spin axes and spin angular velocities must be finite; spin-axis vectors must be non-zero.")
        if self.enable_tides_var.get() and tidal_damping <= 0:
            raise ValueError("Enable a positive tidal damping coefficient or disable tides.")
        if (self.enable_oblateness_var.get() or self.enable_1pn_var.get()) and soft != 0:
            raise ValueError("J2 and 1PN corrections require ε = 0 for a consistent force model. Set softening to zero.")
        if self.com_var.get():
            masses = p[:, 0]
            rcom = (masses[:, None] * p[:, 2:5]).sum(0) / masses.sum()
            vcom = (masses[:, None] * p[:, 5:8]).sum(0) / masses.sum()
            p[:, 2:5] -= rcom
            p[:, 5:8] -= vcom
            for row, vals in zip(self.body_vars, p):
                for k in range(2, 8):
                    row[k].set(_fmt(vals[k]))
        return dict(m=p[:, 0], R=p[:, 1], pos=p[:, 2:5], vel=p[:, 5:8], G=G, dt=dt,
                    steps=steps, soft=soft, rtol=rtol, atol=atol,
                    threshold=threshold, view=view, trails=trails,
                    restitution=restitution, collision=self.collision_var.get(),
                    enable_oblateness=self.enable_oblateness_var.get(), j2=j2, spin_axes=spin_axes,
                    spin_omega=spin_omega, enable_1pn=self.enable_1pn_var.get(), c_light=c_light,
                    tidal_damping=tidal_damping if self.enable_tides_var.get() else 0.0)

    def _on_preset_selected(self, _event=None):
        """Route the model selector to either a built-in preset or editable custom setup.

        Selecting Custom deliberately preserves the values currently in the body fields.
        Use the "Build a new custom model" button to populate fresh example values.
        """
        selected = self.preset_var.get()
        if selected == CUSTOM_PRESET:
            self._custom_model_active = True
            self.system_metadata = {
                "source": "Custom model",
                "preset": CUSTOM_PRESET,
                "epoch": None,
                "names": [],
                "description": "User-defined three-body system.",
            }
            self.preset_info_var.set(
                "Custom model selected. Current body values are preserved. Edit mass, radius, "
                "position (x, y, z) and velocity (vx, vy, vz), then click Apply values & reset."
            )
            self.event_var.set("Custom model selected; existing body values were preserved.")
            return
        self._load_preset()

    def _on_body_field_edited(self, _event=None):
        """Mark hand-edited body parameters as a custom model without resetting fields."""
        if self.preset_var.get() != CUSTOM_PRESET:
            self.preset_var.set(CUSTOM_PRESET)
        self._custom_model_active = True
        self.system_metadata = {
            "source": "Custom model",
            "preset": CUSTOM_PRESET,
            "epoch": None,
            "names": [],
            "description": "User-edited three-body system.",
        }
        self.preset_info_var.set(
            "Custom model: body values have been edited. Click Apply values & reset to simulate them."
        )

    def _start_custom_model(self):
        """Initialize an editable three-body system with useful, safe starting values."""
        self._custom_model_active = True
        self.preset_var.set(CUSTOM_PRESET)
        self.units_var.set(ARBITRARY)
        self.G_var.set("1.0")
        self.dt_var.set("0.002")
        self.steps_var.set("4")
        self.soft_var.set("0.0")
        self.rtol_var.set("1e-9")
        self.atol_var.set("1e-12")
        self.threshold_var.set("0.2")
        self.view_var.set("6.0")
        self.trail_len_var.set("1200")
        self.restitution_var.set("1.0")
        self.integrator_var.set(YOSHIDA)
        self.collision_var.set(PASS)
        self.adaptive_var.set(True)
        self.autozoom_var.set(True)
        self.trail_var.set(True)
        self.floor_var.set(True)
        self.shells_var.set(False)
        self.field_var.set(False)
        self.accel_var.set(False)
        self.com_var.set(True)
        self.enable_oblateness_var.set(False)
        self.enable_1pn_var.set(False)
        self.enable_tides_var.set(False)
        self.c_light_var.set("1000.0")
        self.tidal_damping_var.set("0.05")
        for var in self.j2_vars:
            var.set("0.0")
        for row in self.spin_axis_vars:
            for var, value in zip(row, ("0", "0", "1")):
                var.set(value)
        for row in self.spin_omega_vars:
            for var in row:
                var.set("0")

        # Values are deliberately dimensionless, well separated, and editable.
        # They are a starting system, not a claim that the initial state is periodic.
        starter_bodies = (
            (1.0, 0.12, -2.0, 0.0, 0.0, 0.0, -0.35, 0.0),
            (1.0, 0.12,  2.0, 0.0, 0.0, 0.0,  0.35, 0.0),
            (0.5, 0.10,  0.0, 3.0, 0.6, 0.20, 0.0, 0.0),
        )
        for row_vars, row_values in zip(self.body_vars, starter_bodies):
            for var, value in zip(row_vars, row_values):
                var.set(_fmt(value))
        self.preset_info_var.set(
            "Custom starter system loaded. Edit all three bodies as needed; positions and "
            "velocities are 3D vectors. Press Apply values & reset when ready."
        )
        self.system_metadata = {
            "source": "Custom model",
            "preset": CUSTOM_PRESET,
            "epoch": None,
            "names": ["Custom body 1", "Custom body 2", "Custom body 3"],
            "description": "User-defined three-body system initialized from the custom starter template.",
        }
        self._apply_display_options()
        self._apply_reset(show_errors=False)
        self.event_var.set("New custom model created. Edit body fields and Apply values & reset.")

    def _load_preset(self):
        if self.preset_var.get() not in PRESETS:
            return
        self._custom_model_active = False
        p = PRESETS[self.preset_var.get()]
        self.preset_info_var.set(p.get("description", "Built-in demonstration system. Edit masses, positions, and velocities to experiment."))
        self.system_metadata = {"source": "Built-in preset", "preset": self.preset_var.get(),
                                "epoch": None, "names": [], "description": p.get("description", "")}
        self.units_var.set(p["units"])
        self.G_var.set(_fmt(p["G"]))
        self.dt_var.set(_fmt(p["dt"]))
        self.steps_var.set(str(p["steps"]))
        self.soft_var.set(_fmt(p["soft"]))
        self.threshold_var.set(_fmt(p["threshold"]))
        self.view_var.set(_fmt(p["view"]))
        self.collision_var.set(p["collision"])
        self.enable_oblateness_var.set(False)
        self.enable_1pn_var.set(False)
        self.enable_tides_var.set(False)
        for var in self.j2_vars: var.set("0")
        for row in self.spin_axis_vars:
            for var, value in zip(row, ("0", "0", "1")): var.set(value)
        for row in self.spin_omega_vars:
            for var in row: var.set("0")
        self.tidal_damping_var.set("0.05")
        if p["units"] == ASTRO:
            self.c_light_var.set(_fmt(C_AU_PER_YEAR))
        else:
            self.c_light_var.set("1000")
        self.integrator_var.set(p.get("integrator", YOSHIDA))
        self.adaptive_var.set(p["adaptive"])
        self.autozoom_var.set(p["autozoom"])
        self.shells_var.set(p.get("show_shells", True))
        self.field_var.set(p.get("show_field", True))
        self.floor_var.set(p.get("show_floor", True))
        self.trail_var.set(p.get("show_trails", True))
        # Periodic-orbit seeds use tiny physical radii to avoid altering the
        # point-mass model; exaggerate only their rendered sphere size by default.
        visual_scale = float(p.get("display_scale", 1.8))
        self.display_scale_var.set(visual_scale)
        self.display_scale_label_var.set(f"Visual body scale: {visual_scale:.1f}× (visual only)")
        for row_vars, row_vals in zip(self.body_vars, p["bodies"]):
            for var, value in zip(row_vars, row_vals):
                var.set(_fmt(value))
        self._apply_reset(show_errors=False)

    def _apply_reset(self, show_errors=True):
        try:
            p = self._read_inputs()
            if (p["enable_1pn"] or p["tidal_damping"] > 0.0) and self.integrator_var.get() != RK45:
                self.integrator_var.set(RK45)
                self.adaptive_var.set(True)
            engine = ThreeBodyEngine(p["m"], p["R"], p["pos"], p["vel"], p["G"], p["soft"],
                                     collision=p["collision"], restitution=p["restitution"],
                                     rtol=p["rtol"], atol=p["atol"],
                                     enable_oblateness=p["enable_oblateness"], j2=p["j2"], spin_axes=p["spin_axes"],
                                     spin_omega=p["spin_omega"], enable_1pn=p["enable_1pn"], c_light=p["c_light"],
                                     tidal_damping=p["tidal_damping"])
        except (ValueError, TypeError) as exc:
            if show_errors:
                messagebox.showerror("Invalid simulation values", str(exc), parent=self.root)
            return
        self.engine = engine
        if self.preset_var.get() == CUSTOM_PRESET or self._custom_model_active:
            self._custom_model_active = True
            old_names = self.system_metadata.get("names", []) if isinstance(self.system_metadata, dict) else []
            self.system_metadata = {
                "source": "Custom model",
                "preset": CUSTOM_PRESET,
                "epoch": None,
                "names": old_names if len(old_names) == 3 else ["Custom body 1", "Custom body 2", "Custom body 3"],
                "description": "User-defined three-body system; body fields and simulation settings were applied from the GUI.",
            }
            self.preset_info_var.set("Custom model active. Edit values and apply again to restart from the new initial state.")
        self.initial_snapshot = {
            "m": np.asarray(p["m"], dtype=float).copy(),
            "R": np.asarray(p["R"], dtype=float).copy(),
            "pos": np.asarray(p["pos"], dtype=float).copy(),
            "vel": np.asarray(p["vel"], dtype=float).copy(),
            "G": float(p["G"]), "softening": float(p["soft"]),
            "rtol": float(p["rtol"]), "atol": float(p["atol"]),
            "enable_oblateness": bool(p["enable_oblateness"]), "j2": np.asarray(p["j2"], dtype=float).copy(),
            "spin_axes": np.asarray(p["spin_axes"], dtype=float).copy(),
            "spin_omega": np.asarray(p["spin_omega"], dtype=float).copy(), "enable_1pn": bool(p["enable_1pn"]),
            "c_light": float(p["c_light"]), "tidal_damping": float(p["tidal_damping"]),
        }
        self.dt, self.steps = p["dt"], p["steps"]
        self.threshold, self.fixed_view, self.trail_count = p["threshold"], p["view"], p["trails"]
        self.failed = False
        self.history = History(maxlen=2200)
        self.history.push(self.engine)
        self.scene.display_scale = self.display_scale_var.get()
        self.scene.set_view_mode(self.view_mode_var.get())
        self.scene.view_halfwidth = self.fixed_view
        self.scene.threshold = self.threshold
        self.scene.zone_mode = self.zone_mode_var.get()
        self.scene.set_display_options(display_scale=self.display_scale_var.get(),
                                       show_shells=self.shells_var.get(), show_field=self.field_var.get(),
                                       show_trails=self.trail_var.get(), show_floor=self.floor_var.get(),
                                       show_acceleration=self.accel_var.get(), zone_mode=self.zone_mode_var.get(),
                                       threshold=self.threshold)
        self.scene.reset_trails(self.engine.pos, self.trail_count)
        self.scene.fit_camera(self.engine, view_halfwidth=self.fixed_view, include_shells=self.shells_var.get())
        self.scene.update(self.engine, force_field=True)
        self._update_metrics()
        self._last_event_seen = len(self.engine.events)
        self.event_var.set("No events yet.")
        self.running = True
        self._dirty = False
        self._render_once(force_field=True)
        self._update_status()

    def _update_metrics(self):
        if self.engine is None:
            return
        astro = self.units_var.get() == ASTRO
        for i in range(3):
            if not self.engine.alive[i]:
                self.metric_vars[i].set("Merged / inactive")
                continue
            g, vesc, rho = self.engine.surface_properties(i)
            if astro:
                g_si = g * AU_M / YEAR_S**2
                v_kms = vesc * AU_M / YEAR_S / 1000.0
                rho_si = rho * MSUN_KG / AU_M**3
                self.metric_vars[i].set(f"g={g_si:.4g} m/s²  |  vesc={v_kms:.4g} km/s  |  ρ={rho_si:.4g} kg/m³")
            else:
                self.metric_vars[i].set(f"g={g:.4g} L/T²  |  vesc={vesc:.4g} L/T  |  ρ={rho:.4g} M/L³")

    def _schedule_tick(self):
        if self._closed:
            return
        self.root.after(16 if self.running else 80, self._tick)

    def _tick(self):
        if self._closed or self.engine is None:
            return
        self._frame += 1
        needs_scene_update = self.running or self._dirty
        if self.running and not self.failed:
            # Scale the time step, not the integer step count, so the speed slider
            # remains effective below 0.5x instead of rounding to one full step.
            self.engine.advance(self.steps, self.dt * self.speed_var.get(),
                                self.integrator_var.get(), adaptive=self.adaptive_var.get(), max_wall=0.010)
            self.scene.push_positions(self.engine.pos, self.engine.alive)
            self.history.push(self.engine)
            if self.engine.events and len(self.engine.events) > self._last_event_seen:
                self.event_var.set(self.engine.events[-1][1])
                self._last_event_seen = len(self.engine.events)
            if self.engine.impact:
                self.running = False
                self.event_var.set(self.engine.events[-1][1] if self.engine.events else "Impact detected.")
            if not self.engine.is_healthy():
                self.failed = True
                self.running = False
                self.status_var.set("Numerical instability detected. Reduce Δt or enable adaptive stepping, then reset.")
            if self.autozoom_var.get() and self._frame - self._last_fit_frame > 50:
                pos_extent = float(np.max(np.abs(self.engine.pos[self.engine.alive] - self.engine.center_of_mass())))
                if pos_extent > self.scene.view_halfwidth * 0.94:
                    self.scene.fit_camera(self.engine, view_halfwidth=max(self.scene.view_halfwidth, pos_extent * 1.3),
                                          include_shells=self.shells_var.get())
                    self._last_fit_frame = self._frame
            if self._frame - self._last_metric_update > 15:
                self._update_metrics()
                self._last_metric_update = self._frame
            if self._frame % 6 == 0:
                self._update_graphs()
            self._update_status()
        if needs_scene_update:
            self.scene.update(self.engine, force_field=self._dirty)
            self.scene.render()
            self._dirty = False
        self._schedule_tick()

    def _update_graphs(self):
        self.separation_graph.set_data([list(x) for x in self.history.separations], labels=("1–2", "1–3", "2–3"))
        self.energy_graph.set_data([list(self.history.energy_error)], labels=("|ΔE/E₀|",), logarithmic=True)

    def _update_status(self):
        if not self.engine:
            return
        d = self.engine.pair_distances()
        finite = d[np.isfinite(d)]
        min_sep = float(np.min(finite)) if len(finite) else math.nan
        state = "STOPPED: numerical issue" if self.failed else ("RUNNING" if self.running else ("IMPACT PAUSE" if self.engine.impact else "PAUSED"))
        unit_t = "yr" if self.units_var.get() == ASTRO else "T"
        rk_note = ""
        if self.integrator_var.get() == RK45:
            rk_note = (f"   | RK45 local error = {self.engine.rk45_last_error:.1e}"
                       f"   | accepted/rejected = {self.engine.rk45_accepted_steps}/{self.engine.rk45_rejected_steps}")
        active_physics = []
        if self.engine.enable_oblateness and np.any(np.abs(self.engine.j2) > 0): active_physics.append("J2")
        if self.engine.enable_1pn: active_physics.append("1PN(pairwise)")
        if self.engine.tidal_damping > 0: active_physics.append("tides(radial)")
        if np.any(np.linalg.norm(self.engine.spin_omega, axis=1) > 0): active_physics.append("body spin")
        ext_note = ("   |   " + "+".join(active_physics)) if active_physics else "   |   Newtonian"
        if self.engine.tidal_damping > 0:
            ext_note += f"   |   tidal heat = {self.engine.tidal_energy_dissipated:.3e}"
        if self.engine.enable_1pn:
            ext_note += "   |   energy diagnostic omits 1PN Hamiltonian"
        if self.engine.enable_oblateness and np.any(np.abs(self.engine.j2) > 0):
            ext_note += "   |   J2 spin-axis reaction torque omitted"
        self.status_var.set(
            f"{state} [{self.view_mode_var.get()}]   |   t = {self.engine.t:.5g} {unit_t}   |   |ΔE/E₀| = {self.engine.energy_error():.2e}"
            f"   |   |ΔL/L₀| = {self.engine.angular_momentum_error():.2e}   |   ΔP/P₀ = {self.engine.momentum_error():.2e}"
            f"   |   min separation = {min_sep:.4g}{rk_note}{ext_note}")

    def _render_once(self, force_field=False):
        if self.engine is None or not hasattr(self, "scene"):
            return
        self.scene.update(self.engine, force_field=force_field)
        self.scene.render()
        self._dirty = False

    def _toggle_running(self):
        if self.failed:
            return
        self.running = not self.running
        if self.engine and self.engine.impact and self.running:
            self.engine.impact = False
        self._update_status()

    def _fit_camera(self):
        if self.engine is not None:
            self.scene.fit_camera(self.engine, view_halfwidth=self._safe_float(self.view_var.get(), self.fixed_view),
                                  include_shells=self.shells_var.get())
            self._dirty = True
            self._render_once(force_field=True)

    def _run_validation(self):
        """Run the reproducible numerical checks and show a compact report."""
        from .selftest import run_selftest
        output = io.StringIO()
        try:
            with redirect_stdout(output):
                result = run_selftest(verbose=True)
            report = output.getvalue()
            if len(report) > 12000:
                report = report[-12000:]
            if result == 0:
                messagebox.showinfo("Physics validation passed", report, parent=self.root)
            else:
                messagebox.showwarning("Physics validation reported failures", report, parent=self.root)
        except Exception as exc:
            messagebox.showerror("Physics validation error", f"Validation could not complete:\n{exc}", parent=self.root)

    def _save_png(self):
        path = filedialog.asksaveasfilename(parent=self.root, title="Save 3D view", defaultextension=".png",
                                            filetypes=[("PNG image", "*.png")])
        if path:
            try:
                self.scene.save_png(path)
                self.event_var.set(f"Saved image: {os.path.basename(path)}")
            except Exception as exc:
                messagebox.showerror("Snapshot failed", str(exc), parent=self.root)

    def _export_csv(self):
        if self.engine is None or not self.history.t:
            return
        path = filedialog.asksaveasfilename(parent=self.root, title="Export simulation history", defaultextension=".csv",
                                            filetypes=[("CSV file", "*.csv")])
        if not path:
            return
        headers = ["time", "separation_1_2", "separation_1_3", "separation_2_3", "energy_error", "momentum_error"]
        for i in range(1, 4):
            headers.extend([f"x{i}", f"y{i}", f"z{i}", f"vx{i}", f"vy{i}", f"vz{i}"])
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                for idx, t in enumerate(self.history.t):
                    seps = [s[idx] for s in self.history.separations]
                    pos = self.history.positions[idx]
                    vel = self.history.velocities[idx]
                    row = [t, *seps, self.history.energy_error[idx], self.history.momentum_error[idx]]
                    for i in range(3):
                        row.extend((*pos[i], *vel[i]))
                    writer.writerow(row)
            self.event_var.set(f"Exported CSV: {os.path.basename(path)}")
        except OSError as exc:
            messagebox.showerror("CSV export failed", str(exc), parent=self.root)

    def _on_key(self, event):
        widget = self.root.focus_get()
        if widget is not None and widget.winfo_class() in ("TEntry", "Entry", "TCombobox", "TButton", "TCheckbutton", "TScale"):
            return
        if event.keysym == "space":
            self._toggle_running()
        elif event.keysym.lower() == "r":
            self._apply_reset()
        elif event.keysym == "2":
            self.view_mode_var.set("2D")
            self._apply_view_mode()
        elif event.keysym == "3":
            self.view_mode_var.set("3D")
            self._apply_view_mode()

    def _close(self):
        self._closed = True
        try:
            self.vtk_interactor.Disable()
        except Exception:
            pass
        try:
            self.vtk_render_window.Finalize()
        except Exception:
            pass
        self.root.destroy()
