"""Tkinter control panel and VTK-embedded interactive 3D visualizer."""
from __future__ import annotations
import csv
import copy
import io
import math
import os
from dataclasses import replace
import platform
import re
import threading
import time
from datetime import date, datetime, timezone
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser

import numpy as np
import vtk
import sys
from contextlib import redirect_stdout

from ..physics import (ThreeBodyEngine, History, VERLET, YOSHIDA, RK45, INTEGRATORS,
                      MERGE, BOUNCE, PASS, STOP, FRAGMENT, COLLISION_MODES, ZONE_THRESH,
                      ZONE_ROCHE, ZONE_MODES, AU_M, YEAR_S, MSUN_KG, G_AU_MSUN_YR, C_AU_PER_YEAR)
from ..presets import PRESETS, PRESET_NAMES, ARBITRARY, ASTRO, engine_inputs
from ..body_size import (DEFAULT_SIZE_MODE, DEFAULT_SIZE_VALUE, SIZE_FIXED, SIZE_MULTIPLIER, SIZE_TRUE, UNIT_HINTS,
                         default_sizes, jpl_visual_radii, normalise_sizes, overlap_warnings, sizes_to_payload, validate_size)
from ..camera import (DRAG_ORBIT, DRAG_PAN, DRAG_ZOOM, MACOS_NOTCH, WINDOWS_NOTCH, drag_action, drag_zoom_factor,
                      follow_translation, pan_translation, recentre, wheel_zoom_factor, zoom_about_point)
from ..renderer_vtk import GravityScene
from ..service import SimulationService
from ..application import SimulationController, state_from_inputs
from ..state_io import save_checkpoint, load_checkpoint
from ..setup_io import write_setup_json, read_setup_json
from ..state import BodyState, IntegratorSettings, PhysicsSettings, SimulationState
from ..themes import THEMES, BODY_COLORS, BODY_NAMES
from ..preferences import load_preferences, save_preferences
from .diagnostics_panel import SparkGraph, format_finite, minimum_active_pair_separation
from ..orbital_analysis import barycentric_frame, pairwise_relative_metrics

BODY_FIELDS = ("Mass", "Radius", "x", "y", "z", "vx", "vy", "vz")
CUSTOM_PRESET = "Custom / Build your own"


def _fmt(value):
    return f"{float(value):.9g}"


def _rgba(hex_color):
    v = hex_color.lstrip("#")
    return tuple(int(v[i:i+2], 16) / 255 for i in (0, 2, 4))


class GravityLabApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Gravity Lab 3D | Three-Body Dynamics")
        root.geometry("1650x1000")
        root.minsize(1240, 780)
        self.engine: ThreeBodyEngine | None = None
        self.simulation_service = SimulationService()
        self.controller = SimulationController(self.simulation_service)
        self.history = History(maxlen=2200)
        self.running = False
        self.failed = False
        self._dirty = True
        self._frame = 0
        self._last_metric_update = 0
        self._last_event_seen = 0
        self._last_event_signature = None
        self._last_fit_frame = 0
        self._closed = False
        self._tick_after_id = None
        # Bounded in-memory timeline of complete engine states for reliable rewind.
        self._timeline = []
        self._timeline_index = 0
        self._timeline_maxlen = 1800
        self._timeline_updating = False
        self.timeline_var = tk.DoubleVar(value=0.0)
        self.timeline_label_var = tk.StringVar(value="t = 0")
        self.system_metadata = {"source": "Built-in preset", "epoch": None, "names": []}
        self.initial_snapshot = None
        self.last_reference_report = ""
        self._closest_approach = {}

        self.theme_var = tk.StringVar(value="Dark")
        self.view_mode_var = tk.StringVar(value="3D")
        self.camera_focus_var = tk.StringVar(value="System center")
        self.reference_frame_var = tk.StringVar(value="Inertial frame")
        self._camera_follow_position = None
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
        self.axes_var = tk.BooleanVar(value=True)
        self.shells_var = tk.BooleanVar(value=True)
        self.field_var = tk.BooleanVar(value=True)
        self.accel_var = tk.BooleanVar(value=False)
        self.com_var = tk.BooleanVar(value=True)
        self.speed_var = tk.DoubleVar(value=1.0)
        self.display_scale_var = tk.DoubleVar(value=1.8)
        self.body_vars = [[tk.StringVar(value="0") for _ in BODY_FIELDS] for _ in range(3)]
        self.body_name_vars = [tk.StringVar(value=name.title()) for name in BODY_NAMES]
        self.body_colors = list(BODY_COLORS)
        self.body_color_buttons = []
        self.body_cards = []
        self.body_size_mode_vars = [tk.StringVar(value=DEFAULT_SIZE_MODE) for _ in range(3)]
        self.body_size_value_vars = [tk.StringVar(value=_fmt(DEFAULT_SIZE_VALUE)) for _ in range(3)]
        self.body_size_hint_vars = [tk.StringVar(value=UNIT_HINTS[DEFAULT_SIZE_MODE]) for _ in range(3)]
        self.body_size_entries = []
        self.size_preset_var = tk.StringVar(value=self.SIZE_PRESETS[0])
        self._drag = None  # active mouse drag: {'action', 'x', 'y'}
        for i, name_var in enumerate(self.body_name_vars):
            name_var.trace_add("write", lambda *_args, idx=i: self._update_body_title(idx))
        self.metric_vars = [tk.StringVar(value="g: — | escape: — | density: —") for _ in range(3)]
        self.status_var = tk.StringVar(value="Paused — press Play to start.")
        self.event_var = tk.StringVar(value="No events yet.")
        self.speed_label_var = tk.StringVar(value="1.0×")
        self.display_scale_label_var = tk.StringVar(value="Visual body scale: 1.8×")
        self._event_log_rendered_count = -1

        self._load_user_preferences()
        self._configure_style()
        self._build_ui()
        self._load_preset()
        self.root.bind_all("<Key>", self._on_key)
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self._schedule_tick()

    def _load_user_preferences(self):
        """Restore UI-only preferences without restoring a simulation or body state."""
        preferences = load_preferences()
        if preferences.get("theme") in THEMES:
            self.theme_var.set(preferences["theme"])
        if preferences.get("view_mode") in ("2D", "3D"):
            self.view_mode_var.set(preferences["view_mode"])
        for key, variable in (
            ("speed", self.speed_var), ("display_scale", self.display_scale_var),
            ("trail", self.trail_var), ("floor", self.floor_var), ("axes", self.axes_var),
            ("shells", self.shells_var), ("field", self.field_var), ("accel", self.accel_var),
            ("com", self.com_var), ("autozoom", self.autozoom_var),
            ("view", self.view_var), ("trail_len", self.trail_len_var),
        ):
            if key in preferences:
                try:
                    variable.set(preferences[key])
                except (tk.TclError, ValueError):
                    pass

    def _save_user_preferences(self):
        """Persist stable UI choices; simulation initial conditions use setup/checkpoint files."""
        preferences = {
            "schema_version": 1,
            "theme": self.theme_var.get() if self.theme_var.get() in THEMES else "Dark",
            "view_mode": self.view_mode_var.get() if self.view_mode_var.get() in ("2D", "3D") else "3D",
            "speed": float(self.speed_var.get()),
            "display_scale": float(self.display_scale_var.get()),
            "trail": bool(self.trail_var.get()), "floor": bool(self.floor_var.get()),
            "axes": bool(self.axes_var.get()), "shells": bool(self.shells_var.get()),
            "field": bool(self.field_var.get()), "accel": bool(self.accel_var.get()),
            "com": bool(self.com_var.get()), "autozoom": bool(self.autozoom_var.get()),
            "view": str(self.view_var.get()), "trail_len": str(self.trail_len_var.get()),
        }
        save_preferences(preferences)

    def _configure_style(self):
        self.palette = THEMES.get(self.theme_var.get(), THEMES["Dark"])
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
        style.configure("Section.TLabel", background=p["panel_bg"], foreground=p["muted"],
                        font=("Segoe UI", 8, "bold"))
        style.configure("TLabelframe", background=p["panel_bg"], foreground=p["text"], bordercolor=p["border"])
        style.configure("TLabelframe.Label", background=p["panel_bg"], foreground=p["muted"], font=("Segoe UI", 9, "bold"))
        for i, color in enumerate(getattr(self, "body_colors", BODY_COLORS), start=1):
            style.configure(f"Body{i}.TLabelframe", background=p["panel_bg"], bordercolor=p["border"])
            style.configure(f"Body{i}.TLabelframe.Label", background=p["panel_bg"], foreground=color, font=("Segoe UI", 9, "bold"))
            style.configure(f"Body{i}.Panel.TLabel", background=p["panel_bg"], foreground=color, font=("Segoe UI", 9))
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
        files.add_command(label="Save exact simulation checkpoint…", command=self._save_checkpoint_dialog)
        files.add_command(label="Load simulation checkpoint…", command=self._load_checkpoint_dialog)
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
            self.scene.fit_camera(self._display_frame(), view_halfwidth=self._safe_float(self.view_var.get(), self.fixed_view),
                                  include_shells=self.shells_var.get())
            self._camera_follow_position = None
        self._dirty = True
        self._render_once(force_field=True)
        self.event_var.set(f"Visualizer switched to {self.view_mode_var.get()} view.")

    def _open_advanced_physics_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Advanced physics models")
        dialog.transient(self.root)
        dialog.geometry("900x730")
        dialog.minsize(640, 420)

        # Put the entire settings form in a canvas so the dialog remains usable
        # on smaller displays and at higher Windows display scaling. Bind wheel
        # events to the canvas/content, not globally, so other app widgets keep
        # their normal scrolling behavior.
        container = ttk.Frame(dialog)
        container.pack(fill=tk.BOTH, expand=True)
        canvas = tk.Canvas(container, highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(container, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        frame = ttk.Frame(canvas, padding=14)
        content_window = canvas.create_window((0, 0), window=frame, anchor="nw")

        def update_scroll_region(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            # Keep the form the same width as the visible canvas.
            canvas.itemconfigure(content_window, width=max(1, canvas.winfo_width()))

        def scroll_with_wheel(event):
            if getattr(event, "num", None) == 4:  # X11 wheel up
                canvas.yview_scroll(-3, "units")
            elif getattr(event, "num", None) == 5:  # X11 wheel down
                canvas.yview_scroll(3, "units")
            elif getattr(event, "delta", 0):  # Windows/macOS wheel
                amount = -1 * int(event.delta / 120) if abs(event.delta) >= 120 else (-1 if event.delta > 0 else 1)
                canvas.yview_scroll(amount * 3, "units")
            return "break"

        frame.bind("<Configure>", update_scroll_region)
        canvas.bind("<Configure>", update_scroll_region)
        for widget in (canvas, frame):
            widget.bind("<MouseWheel>", scroll_with_wheel, add="+")
            widget.bind("<Button-4>", scroll_with_wheel, add="+")
            widget.bind("<Button-5>", scroll_with_wheel, add="+")
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
            "F — Fit view to the system\nC — Re-centre the camera on the focused body\n"
            "Preset search — type a name, family or description in the Search presets field\n"
            "3D view: drag — rotate; Shift+drag or middle-drag — pan; right-drag — zoom\n2D view: drag — pan (the plane never rotates); right-drag — zoom\nMouse wheel — Zoom toward the cursor\nBody card → Visual size — set each body's on-screen size (display only)\n"
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
                         "accel_var", "axes_var", "com_var")
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
            "body_names": [var.get().strip() for var in self.body_name_vars],
            "body_colors": list(self.body_colors),
            "body_sizes": sizes_to_payload(self._current_body_sizes()),
            "settings": settings,
            "metadata": self.system_metadata,
            "saved_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        try:
            write_setup_json(path, payload)
            self.event_var.set(f"Saved setup: {os.path.basename(path)}")
        except OSError as exc:
            messagebox.showerror("Save setup failed", str(exc), parent=self.root)

    def _load_setup_json(self):
        path = filedialog.askopenfilename(parent=self.root, title="Load system setup",
            filetypes=[("Gravity Lab setup", "*.json"), ("JSON", "*.json")])
        if not path:
            return
        try:
            payload = read_setup_json(path)
            bodies = payload["bodies"]
            for row_vars, row_values in zip(self.body_vars, bodies):
                for variable, value in zip(row_vars, row_values):
                    variable.set(str(value))
            saved_names = payload.get("body_names", [])
            if isinstance(saved_names, list) and len(saved_names) == 3:
                for variable, value in zip(self.body_name_vars, saved_names):
                    variable.set(str(value).strip() or "Body")
            saved_colors = payload.get("body_colors", [])
            if isinstance(saved_colors, list) and len(saved_colors) == 3 and all(
                isinstance(c, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", c) for c in saved_colors
            ):
                self.body_colors = [c.lower() for c in saved_colors]
                self._apply_body_colors()
            # Older setup files have no body_sizes key; they load with default (true-scale) sizes.
            self._set_body_size_vars(normalise_sizes(payload.get("body_sizes"), 3))
            setting_vars = {
                "units": self.units_var, "G": self.G_var, "dt": self.dt_var, "steps": self.steps_var,
                "soft": self.soft_var, "rtol": self.rtol_var, "atol": self.atol_var,
                "threshold": self.threshold_var, "view": self.view_var, "trail_len": self.trail_len_var,
                "restitution": self.restitution_var, "integrator": self.integrator_var,
                "collision": self.collision_var, "zone_mode": self.zone_mode_var,
            }
            setting_vars.update({"adaptive": self.adaptive_var, "autozoom": self.autozoom_var,
                                 "trail": self.trail_var, "floor": self.floor_var, "shells": self.shells_var,
                                 "field": self.field_var, "accel": self.accel_var, "axes": self.axes_var, "com": self.com_var})
            settings = payload.get("settings", {})
            for key, variable in setting_vars.items():
                if key in settings:
                    variable.set(settings[key])
            # Backward-compatible schema-1 setup files predate the axes toggle.
            if "axes" not in settings:
                self.axes_var.set(True)
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
            self._apply_body_colors()
            self._apply_reset()
            self.event_var.set(f"Loaded setup: {os.path.basename(path)}")
        except Exception as exc:
            messagebox.showerror("Load setup failed", str(exc), parent=self.root)

    def _save_checkpoint_dialog(self):
        path = filedialog.asksaveasfilename(
            parent=self.root, title="Save exact simulation checkpoint",
            defaultextension=".glcheckpoint.json",
            filetypes=[("Gravity Lab checkpoint", "*.glcheckpoint.json"), ("JSON", "*.json")],
        )
        if not path:
            return
        try:
            save_checkpoint(self.simulation_service, path)
            self.event_var.set(f"Saved simulation checkpoint: {os.path.basename(path)}")
        except (OSError, ValueError, RuntimeError) as exc:
            messagebox.showerror("Checkpoint save failed", str(exc), parent=self.root)

    def _load_checkpoint_dialog(self):
        path = filedialog.askopenfilename(
            parent=self.root, title="Load exact simulation checkpoint",
            filetypes=[("Gravity Lab checkpoint", "*.glcheckpoint.json"), ("JSON", "*.json")],
        )
        if not path:
            return
        try:
            restored = load_checkpoint(path)
            state = restored.state
            engine = restored.engine
            if state is None or engine is None:
                raise ValueError("Checkpoint does not contain a configured simulation.")
            self.simulation_service = restored
            self.controller = SimulationController(restored)
            self.engine = engine
            self.running = False
            self.failed = not engine.is_healthy()
            self.dt = state.integrator.dt
            self.steps = state.integrator.steps_per_frame
            self._last_event_seen = len(engine.events)
            self._last_event_signature = engine.events[-1] if engine.events else None
            self.units_var.set(state.physics.units)
            self.G_var.set(_fmt(state.physics.gravitational_constant))
            self.dt_var.set(_fmt(state.integrator.dt))
            self.steps_var.set(str(state.integrator.steps_per_frame))
            self.soft_var.set(_fmt(state.physics.softening))
            self.rtol_var.set(_fmt(state.integrator.rtol))
            self.atol_var.set(_fmt(state.integrator.atol))
            self.integrator_var.set(state.integrator.method)
            self.adaptive_var.set(state.integrator.adaptive)
            self.collision_var.set(state.physics.collision_mode)
            self.restitution_var.set(_fmt(state.physics.restitution))
            self.enable_oblateness_var.set(state.physics.enable_oblateness)
            self.enable_1pn_var.set(state.physics.enable_1pn)
            self.enable_tides_var.set(state.physics.tidal_damping > 0.0)
            self.c_light_var.set(_fmt(state.physics.c_light))
            self.tidal_damping_var.set(_fmt(state.physics.tidal_damping))
            for i, body in enumerate(state.bodies):
                self.body_name_vars[i].set(body.name)
                self.body_colors[i] = body.color
                self.body_size_mode_vars[i].set(body.size_mode)
                self.body_size_value_vars[i].set(_fmt(body.size_value))
                values = (body.mass, body.radius, *body.position, *body.velocity)
                for var, value in zip(self.body_vars[i], values):
                    var.set(_fmt(value))
                self.j2_vars[i].set(_fmt(body.j2))
                for var, value in zip(self.spin_axis_vars[i], body.spin_axis):
                    var.set(_fmt(value))
                for var, value in zip(self.spin_omega_vars[i], body.spin_omega):
                    var.set(_fmt(value))
            self._apply_body_colors()
            self._refresh_body_size_widgets()
            self._apply_body_sizes(render=False)
            self._custom_model_active = True
            self.preset_var.set(CUSTOM_PRESET)
            self.preset_info_var.set("Exact simulation checkpoint loaded. The simulation is paused at the saved time.")
            self.system_metadata = {"source": "Loaded simulation checkpoint", "preset": CUSTOM_PRESET,
                                    "epoch": None, "names": [body.name for body in state.bodies]}
            self.history = History(maxlen=2200)
            self.history.push(engine)
            self._timeline = []
            self._timeline_index = 0
            self._record_timeline_state(force=True)
            self.scene.reset_trails(engine.pos, max_trails=self.trail_count)
            self.scene.push_positions(engine.pos, engine.alive)
            self._apply_display_options()
            self._update_metrics()
            self._update_graphs()
            self._refresh_event_log()
            self._dirty = True
            self.event_var.set(f"Loaded checkpoint at t={engine.t:.9g}; simulation paused.")
        except (OSError, ValueError, RuntimeError, TypeError) as exc:
            messagebox.showerror("Checkpoint load failed", str(exc), parent=self.root)

    def _open_horizons_import_dialog(self):
        from ..ephemeris import SOLAR_SYSTEM_BODIES
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
                    from ..ephemeris import fetch_three_body_horizons
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
            self.body_name_vars[i].set(str(result.names[i]))
        # JPL vectors use AU-scale separations. The generic scene visibility
        # floor can make Earth and Moon appear to overlap, so assign explicit
        # display-only radii based on their separation. Physics radii stay intact.
        visual_sizes = jpl_visual_radii(
            result.names, result.radii, result.positions,
            global_scale=float(self.display_scale_var.get()),
        )
        self._set_body_size_vars(visual_sizes)
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
        view_combo.pack(side=tk.LEFT, padx=(0, 8))
        view_combo.bind("<<ComboboxSelected>>", lambda _e: self._apply_view_mode())
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=2)
        ttk.Button(toolbar, text="Advanced physics…", command=self._open_advanced_physics_dialog).pack(side=tk.LEFT, padx=3)
        ttk.Button(toolbar, text="Pause / Play", command=self._toggle_running).pack(side=tk.LEFT, padx=3)
        ttk.Button(toolbar, text="Reset simulation", command=self._apply_reset).pack(side=tk.LEFT, padx=3)
        ttk.Button(toolbar, text="Fit view", command=self._fit_camera).pack(side=tk.LEFT, padx=3)
        ttk.Label(toolbar, text="Focus", style="Panel.TLabel").pack(side=tk.LEFT, padx=(8, 3))
        self.camera_focus_combo = ttk.Combobox(toolbar, textvariable=self.camera_focus_var,
                                               values=("System center",), state="readonly", width=13)
        self.camera_focus_combo.pack(side=tk.LEFT, padx=3)
        self.camera_focus_combo.bind("<<ComboboxSelected>>", self._on_camera_focus_changed)
        ttk.Label(toolbar, text="Reference", style="Panel.TLabel").pack(side=tk.LEFT, padx=(6, 3))
        self.reference_frame_combo = ttk.Combobox(toolbar, textvariable=self.reference_frame_var,
                                                   values=("Inertial frame",), state="readonly", width=13)
        self.reference_frame_combo.pack(side=tk.LEFT, padx=3)
        self.reference_frame_combo.bind("<<ComboboxSelected>>", self._on_reference_frame_changed)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=2)
        ttk.Label(toolbar, text="Speed", style="Panel.TLabel").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Scale(toolbar, from_=0.1, to=5.0, variable=self.speed_var, orient=tk.HORIZONTAL,
                  length=115, command=self._on_speed).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Label(toolbar, textvariable=self.speed_label_var, style="Panel.TLabel", width=13).pack(side=tk.LEFT)

        timeline_bar = ttk.Frame(outer, style="Panel.TFrame", padding=(8, 4))
        timeline_bar.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(timeline_bar, text="Step −", command=self._step_backward).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(timeline_bar, text="Step +", command=self._step_forward).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(timeline_bar, text="Timeline", style="Panel.TLabel").pack(side=tk.LEFT, padx=(0, 6))
        self.timeline_scale = ttk.Scale(timeline_bar, from_=0, to=0, variable=self.timeline_var,
                                        orient=tk.HORIZONTAL, command=self._on_timeline_seek)
        self.timeline_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Label(timeline_bar, textvariable=self.timeline_label_var, style="Panel.TLabel", width=22).pack(side=tk.RIGHT, padx=(8, 0))

        # The horizontal sash makes the setup panel independently resizable.
        content = ttk.Panedwindow(outer, orient=tk.HORIZONTAL)
        content.pack(fill=tk.BOTH, expand=True)
        self.content_panes = content
        side_shell = ttk.Frame(content, width=395)
        side_shell.pack_propagate(False)
        self.side_shell = side_shell
        self.side_canvas = tk.Canvas(side_shell, bg=self.palette["app_bg"], highlightthickness=0, width=385)
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
        self.main_panel = main
        content.add(side_shell, weight=0)
        content.add(main, weight=1)

        # Vertical sash lets users trade viewport area for larger diagnostics.
        self.main_panes = ttk.Panedwindow(main, orient=tk.VERTICAL)
        self.main_panes.pack(fill=tk.BOTH, expand=True)
        viewport_frame = ttk.Frame(self.main_panes, style="Panel.TFrame")
        diagnostics_frame = ttk.Frame(self.main_panes, style="Panel.TFrame", padding=(2, 2, 2, 0))
        self.main_panes.add(viewport_frame, weight=4)
        self.main_panes.add(diagnostics_frame, weight=1)

        # Embed the native VTK child window in its own resizable pane.
        self.vtk_canvas = tk.Canvas(viewport_frame, bg=self.palette["plot_bg"], highlightthickness=0, takefocus=1)
        self.vtk_canvas.pack(fill=tk.BOTH, expand=True)
        self.vtk_canvas.update_idletasks()
        self.vtk_render_window = self._new_native_render_window()
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

        self.status = ttk.Label(diagnostics_frame, textvariable=self.status_var, style="Panel.TLabel",
                                anchor="w", justify=tk.LEFT, wraplength=1200)
        self.status.pack(side=tk.TOP, fill=tk.X, pady=(1, 4))
        self.status.bind("<Configure>", lambda event: self.status.configure(wraplength=max(320, event.width - 12)))
        self.diagnostics_notebook = ttk.Notebook(diagnostics_frame)
        self.diagnostics_notebook.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.graph_frame = ttk.Frame(self.diagnostics_notebook, style="Panel.TFrame")  # compatibility/theme parent

        tab_specs = [
            ("Pair separations", "PAIR SEPARATIONS", ("#9fb3c8", "#f6bd60", "#84a59d")),
            ("Energy drift", "ENERGY DRIFT |log10|", ("#c77dff",)),
            ("Momentum drift", "LINEAR MOMENTUM DRIFT |log10|", ("#5ea1ff",)),
            ("Angular momentum", "ANGULAR MOMENTUM DRIFT |log10|", ("#f08b67",)),
        ]
        self.diagnostic_graphs = {}
        for tab_label, title, colors in tab_specs:
            tab = ttk.Frame(self.diagnostics_notebook, style="Panel.TFrame")
            self.diagnostics_notebook.add(tab, text=tab_label)
            graph = SparkGraph(tab, title, colors, height=205, background=self.palette["panel_bg"])
            graph.pack(fill=tk.BOTH, expand=True)
            self.diagnostic_graphs[tab_label] = graph
        self.separation_graph = self.diagnostic_graphs["Pair separations"]
        self.energy_graph = self.diagnostic_graphs["Energy drift"]
        self.momentum_graph = self.diagnostic_graphs["Momentum drift"]
        self.angular_momentum_graph = self.diagnostic_graphs["Angular momentum"]

        events_tab = ttk.Frame(self.diagnostics_notebook, style="Panel.TFrame", padding=4)
        self.diagnostics_notebook.add(events_tab, text="Collision events")
        self.event_text = tk.Text(events_tab, height=5, wrap=tk.WORD, relief=tk.FLAT,
                                  background=self.palette["entry_bg"], foreground=self.palette["text"],
                                  insertbackground=self.palette["text"], font=("Consolas", 9),
                                  borderwidth=0, padx=6, pady=5, state=tk.DISABLED)
        event_scroll = ttk.Scrollbar(events_tab, orient=tk.VERTICAL, command=self.event_text.yview)
        self.event_text.configure(yscrollcommand=event_scroll.set)
        event_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.event_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._refresh_event_log()

        self.root.after_idle(self._set_initial_pane_positions)
        self.apply_theme_widgets()

    def _set_initial_pane_positions(self):
        """Set useful starting sash sizes while leaving both panes user-resizable."""
        try:
            if self.content_panes.winfo_width() > 700:
                self.content_panes.sashpos(0, 395)
            height = self.main_panes.winfo_height()
            if height > 420:
                self.main_panes.sashpos(0, max(330, height - 245))
            self._resize_vtk()
        except tk.TclError:
            pass

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
        self.vtk_canvas.bind("<Button-4>", lambda e: self._vtk_wheel(e, direction=1))
        self.vtk_canvas.bind("<Button-5>", lambda e: self._vtk_wheel(e, direction=-1))

    _MOUSE_BUTTONS = {"Left": 1, "Middle": 2, "Right": 3}

    def _vtk_mouse(self, event, vtk_event):
        """Route viewport mouse events.

        Only *orbit* drags (left button in the 3D view) are handed to the VTK
        trackball style.  Panning and zooming are done here so that:

        * the 2D view never rotates: left/middle drag pans, right drag zooms;
        * the 3D view can be panned with middle drag or Shift+left drag (so a
          laptop touchpad without a middle button works), and right drag zooms
          toward the cursor exactly like the wheel.

        The decision logic is in :func:`gravity_lab.camera.drag_action`.
        """
        try:
            self.vtk_canvas.focus_set()
            if vtk_event.endswith("ButtonPressEvent"):
                button = self._MOUSE_BUTTONS.get(vtk_event[:-len("ButtonPressEvent")])
                state = int(getattr(event, "state", 0) or 0)
                action = drag_action(self.view_mode_var.get(), button, shift=bool(state & 0x1), ctrl=bool(state & 0x4))
                if action is None:
                    self._drag = None
                    return
                self._drag = {"action": action, "button": button, "x": event.x, "y": event.y,
                              "anchor": self._cursor_on_focal_plane(event.x, event.y)}
                if action == DRAG_ORBIT:
                    self._forward_to_vtk(event, vtk_event)
            elif vtk_event.endswith("ButtonReleaseEvent"):
                drag, self._drag = self._drag, None
                if drag is not None and drag["action"] == DRAG_ORBIT:
                    self._forward_to_vtk(event, vtk_event)
            elif vtk_event == "MouseMoveEvent":
                drag = self._drag
                if drag is None:
                    return  # plain hover: nothing for the camera to do
                dx, dy = event.x - drag["x"], event.y - drag["y"]
                if drag["action"] == DRAG_ORBIT:
                    self._forward_to_vtk(event, vtk_event)
                elif drag["action"] == DRAG_PAN:
                    self._pan_camera(dx, dy)
                elif drag["action"] == DRAG_ZOOM:
                    self._zoom_camera(drag_zoom_factor(dy), drag["anchor"])
                drag["x"], drag["y"] = event.x, event.y
        except (AttributeError, RuntimeError, ValueError, TypeError):
            pass

    def _forward_to_vtk(self, event, vtk_event):
        height = max(1, self.vtk_canvas.winfo_height())
        # Modifier keys are routed by drag_action; VTK must only ever see a plain orbit.
        self.vtk_interactor.SetShiftKey(0)
        self.vtk_interactor.SetControlKey(0)
        self.vtk_interactor.SetEventPosition(int(event.x), int(height - event.y))
        getattr(self.vtk_interactor, vtk_event)()

    def _cursor_on_focal_plane(self, x_tk, y_tk):
        """World point under a Tk canvas pixel, on the plane through the focal point."""
        renderer = self.scene.renderer
        camera = renderer.GetActiveCamera()
        canvas_w = max(1, self.vtk_canvas.winfo_width())
        canvas_h = max(1, self.vtk_canvas.winfo_height())
        # Use render-window dimensions for VTK display coordinates. Tk and
        # VTK sizes can differ slightly on Windows with display scaling.
        rw_w, rw_h = self.vtk_render_window.GetSize()
        rw_w, rw_h = max(1, int(rw_w)), max(1, int(rw_h))
        x = min(max(int(round(float(x_tk) * rw_w / canvas_w)), 0), rw_w - 1)
        y = min(max(int(round((canvas_h - 1 - float(y_tk)) * rw_h / canvas_h)), 0), rw_h - 1)
        focal = np.asarray(camera.GetFocalPoint(), dtype=float)
        renderer.SetWorldPoint(float(focal[0]), float(focal[1]), float(focal[2]), 1.0)
        renderer.WorldToDisplay()
        focal_display = renderer.GetDisplayPoint()
        renderer.SetDisplayPoint(float(x), float(y), float(focal_display[2]))
        renderer.DisplayToWorld()
        world_h = np.asarray(renderer.GetWorldPoint(), dtype=float)
        if abs(float(world_h[3])) > 1e-15:
            return world_h[:3] / world_h[3]
        return world_h[:3]

    def _zoom_camera(self, factor, anchor):
        """Zoom so ``anchor`` (a focal-plane world point) stays fixed on screen."""
        renderer = self.scene.renderer
        camera = renderer.GetActiveCamera()
        parallel = bool(camera.GetParallelProjection())
        new_position, new_focal, new_scale, applied = zoom_about_point(
            camera.GetPosition(), camera.GetFocalPoint(), anchor, factor, parallel,
            camera.GetParallelScale(), self.scene.view_halfwidth)
        if applied == 1.0:
            return
        camera.SetPosition(*new_position)
        camera.SetFocalPoint(*new_focal)
        if parallel:
            camera.SetParallelScale(float(new_scale))
        renderer.ResetCameraClippingRange()
        self._dirty = True
        self._render_once()

    def _pan_camera(self, dx_pixels, dy_pixels):
        """Translate the camera in the view plane; orientation is never changed."""
        renderer = self.scene.renderer
        camera = renderer.GetActiveCamera()
        translation = pan_translation(
            dx_pixels, dy_pixels, self.vtk_canvas.winfo_height(), camera.GetPosition(), camera.GetFocalPoint(),
            camera.GetViewUp(), bool(camera.GetParallelProjection()), camera.GetParallelScale(), camera.GetViewAngle())
        if not np.any(translation):
            return
        camera.SetPosition(*(np.asarray(camera.GetPosition(), dtype=float) + translation))
        camera.SetFocalPoint(*(np.asarray(camera.GetFocalPoint(), dtype=float) + translation))
        renderer.ResetCameraClippingRange()
        self._dirty = True
        self._render_once()

    def _vtk_wheel(self, event, direction=None):
        """Zoom toward the cursor (anchored on the focal plane, not on a picked surface).

        Do not pick a body surface here: using a surface at a different depth
        makes the camera jump when zooming.  The focal-plane anchor gives a
        stable CAD-style zoom and works even when the cursor is over empty space.
        The maths lives in :mod:`gravity_lab.camera`; it also handles the 2D
        (parallel-projection) view, where ``Dolly`` has no visible effect.
        """
        try:
            notch = MACOS_NOTCH if sys.platform == "darwin" else WINDOWS_NOTCH
            factor = wheel_zoom_factor(delta=getattr(event, "delta", None), direction=direction, notch_size=notch)
            self._zoom_camera(factor, self._cursor_on_focal_plane(event.x, event.y))
        except (AttributeError, RuntimeError, ValueError, ZeroDivisionError, TypeError):
            # Keep mouse-wheel interaction safe if VTK is mid-resize/rebuild.
            pass
        return "break"

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
        """Compose the sidebar from focused, reusable UI panel modules."""
        from .preset_panel import build_preset_panel
        from .settings_panel import build_body_editor_panel, build_settings_panel

        side = self.side_inner
        build_preset_panel(self, side, custom_preset=CUSTOM_PRESET)
        build_body_editor_panel(self, side)
        build_settings_panel(self, side)

    @staticmethod
    def _add_combo_row(parent, row, label, variable, values, callback=None):
        ttk.Label(parent, text=label, style="Panel.TLabel").grid(row=row, column=0, sticky="w", padx=(0, 6), pady=2)
        combo = ttk.Combobox(parent, textvariable=variable, values=values, state="readonly", width=26)
        combo.grid(row=row, column=1, sticky="ew", pady=2)
        if callback:
            combo.bind("<<ComboboxSelected>>", lambda _e: callback())
        return combo

    def apply_theme_widgets(self):
        self.palette = THEMES.get(self.theme_var.get(), THEMES["Dark"])
        p = self.palette
        self.root.configure(bg=p["app_bg"])
        self.side_canvas.configure(bg=p["app_bg"])
        for graph in getattr(self, "diagnostic_graphs", {}).values():
            graph.set_theme(p)
        if hasattr(self, "event_text"):
            self.event_text.configure(background=p["entry_bg"], foreground=p["text"],
                                      insertbackground=p["text"])
        self._apply_body_colors()
        if hasattr(self, "scene"):
            self.scene.set_theme(self.theme_var.get())
            self.scene.set_body_colors(self.body_colors)
            self._dirty = True

    def _apply_theme(self):
        self._configure_style()
        self.apply_theme_widgets()
        self._render_once(force_field=True)

    def _update_body_title(self, index):
        """Keep the body-card title in sync with its editable display name."""
        name = self.body_name_vars[index].get().strip() or f"Body {index + 1}"
        if hasattr(self, "body_cards") and index < len(self.body_cards):
            try:
                self.body_cards[index].configure(text=f"BODY {index + 1} · {name}")
            except tk.TclError:
                pass
        if isinstance(self.system_metadata, dict):
            names = [v.get().strip() or f"Body {j + 1}" for j, v in enumerate(self.body_name_vars)]
            self.system_metadata["names"] = names

    def _customize_body(self, index):
        """Open the native color wheel/dialog for the chosen body's display color."""
        name = self.body_name_vars[index].get().strip() or f"Body {index + 1}"
        chosen = colorchooser.askcolor(
            color=self.body_colors[index], title=f"Choose colour for {name}", parent=self.root
        )
        if not chosen or not chosen[1]:
            return
        self.body_colors[index] = chosen[1].lower()
        self._apply_body_colors()
        self._dirty = True
        if hasattr(self, "scene"):
            self.scene.set_body_colors(self.body_colors)
            self._render_once(force_field=False)
        self.event_var.set(f"Updated appearance for {name}.")

    def _apply_body_colors(self):
        """Refresh swatches, metric accents, and the 3D actors after a color edit."""
        if hasattr(self, "body_color_buttons"):
            p = getattr(self, "palette", THEMES["Dark"])
            for i, button in enumerate(self.body_color_buttons):
                if i >= len(self.body_colors):
                    continue
                color = self.body_colors[i]
                try:
                    button.configure(foreground=color, activeforeground=color,
                                     background=p["panel_bg"], activebackground=p["button_active"])
                except tk.TclError:
                    pass
        try:
            style = ttk.Style()
            p = getattr(self, "palette", THEMES["Dark"])
            for i, color in enumerate(self.body_colors, start=1):
                style.configure(f"Body{i}.Panel.TLabel", background=p["panel_bg"], foreground=color)
                style.configure(f"Body{i}.TLabelframe.Label", background=p["panel_bg"], foreground=color)
        except tk.TclError:
            pass
        if hasattr(self, "scene"):
            self.scene.set_body_colors(self.body_colors)

    def _on_mousewheel(self, event):
        try:
            # Only scroll the sidebar when the pointer is actually over it; the
            # viewport and diagnostics area must not scroll it as a side effect.
            under_pointer = self.side_canvas.winfo_containing(event.x_root, event.y_root)
            if under_pointer is not None and str(under_pointer).startswith(str(self.side_canvas)):
                notch = MACOS_NOTCH if sys.platform == "darwin" else WINDOWS_NOTCH
                steps = -event.delta / notch
                self.side_canvas.yview_scroll(int(math.copysign(max(1, abs(round(steps))), steps)) if steps else 0, "units")
        except (tk.TclError, AttributeError):
            pass

    def _unit_changed(self):
        self.G_var.set(_fmt(G_AU_MSUN_YR if self.units_var.get() == ASTRO else 1.0))
        self.c_light_var.set(_fmt(C_AU_PER_YEAR if self.units_var.get() == ASTRO else 1000.0))

    def _on_speed(self, value):
        self.speed_label_var.set(f"{float(value):.1f}×")

    def _on_display_scale(self, value):
        self.display_scale_label_var.set(f"Visual body scale: {float(value):.1f}× (visual only)")
        self._apply_display_options()

    def _apply_display_options(self):
        if not hasattr(self, "scene"):
            return
        self.scene.set_display_options(
            display_scale=self.display_scale_var.get(), show_shells=self.shells_var.get(),
            show_field=self.field_var.get(), show_trails=self.trail_var.get(),
            show_floor=self.floor_var.get(), show_acceleration=self.accel_var.get(), show_axes=self.axes_var.get(),
            zone_mode=self.zone_mode_var.get(), threshold=self._safe_float(self.threshold_var.get(), 0.2))
        self._dirty = True
        if not self.running:
            self._render_once(force_field=True)

    # ---- per-body visual size (display only; never changes the physics) ------------
    SIZE_PRESETS = ("Custom (per body)", "Realistic (true scale)", "Exaggerated (×5)", "Uniform (equal size)")

    def _current_body_sizes(self, strict=False):
        """Return three validated (mode, value) pairs from the size widgets.

        While the user is typing, an incomplete value silently keeps the last
        valid size.  With ``strict=True`` (used when applying/resetting) an
        invalid value raises ``ValueError`` so the usual error dialog explains it.
        """
        fallback = getattr(self, "_last_valid_sizes", None) or default_sizes(3)
        sizes = []
        for i in range(3):
            mode = self.body_size_mode_vars[i].get()
            name = self.body_name_vars[i].get().strip() or f"Body {i + 1}"
            if mode == SIZE_TRUE:  # the value box is disabled and ignored in this mode
                sizes.append((SIZE_TRUE, DEFAULT_SIZE_VALUE))
                continue
            try:
                sizes.append(validate_size(mode, self.body_size_value_vars[i].get(), name))
            except ValueError:
                if strict:
                    raise
                sizes.append(fallback[i])
        return sizes

    def _set_body_size_vars(self, sizes, render=False):
        for i, (mode, value) in enumerate(sizes):
            self.body_size_mode_vars[i].set(mode)
            self.body_size_value_vars[i].set(_fmt(value))
        self.size_preset_var.set(self.SIZE_PRESETS[0])
        self._refresh_body_size_widgets()
        self._apply_body_sizes(render=render)

    def _refresh_body_size_widgets(self):
        for i in range(3):
            mode = self.body_size_mode_vars[i].get()
            hint = UNIT_HINTS.get(mode, "")
            if mode != SIZE_TRUE:
                try:
                    validate_size(mode, self.body_size_value_vars[i].get())
                except ValueError:
                    hint = "enter a number > 0"
            self.body_size_hint_vars[i].set(hint)
            if i < len(self.body_size_entries):
                self.body_size_entries[i].configure(state="disabled" if mode == SIZE_TRUE else "normal")

    def _apply_body_sizes(self, render=True):
        """Push the current sizes to the renderer and the application state, live."""
        self._refresh_body_size_widgets()
        sizes = self._current_body_sizes()
        self._last_valid_sizes = list(sizes)
        if hasattr(self, "scene"):
            self.scene.set_body_sizes(sizes)
        service = getattr(self, "simulation_service", None)
        if service is not None:
            service.set_body_sizes(sizes)
        if render and hasattr(self, "scene") and getattr(self, "engine", None) is not None:
            self._dirty = True
            self._render_once()

    def _on_body_size_changed(self, _index=None):
        self._refresh_body_size_widgets()
        self.size_preset_var.set(self.SIZE_PRESETS[0])
        self._apply_body_sizes()

    def _apply_size_preset(self):
        choice = self.size_preset_var.get()
        if choice == self.SIZE_PRESETS[1]:
            sizes = default_sizes(3)
        elif choice == self.SIZE_PRESETS[2]:
            sizes = [(SIZE_MULTIPLIER, 5.0)] * 3
        elif choice == self.SIZE_PRESETS[3]:
            sizes = [(SIZE_FIXED, 0.03 * max(float(self.scene.view_halfwidth), 1.0))] * 3
        else:
            return
        self._set_body_size_vars(sizes)
        self.size_preset_var.set(choice)
        self._apply_body_sizes()

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
        for i, name_var in enumerate(self.body_name_vars):
            name_var.set(f"Custom body {i + 1}")
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
        # A preset brings its own physical scale, so per-body visual overrides from the
        # previous system (e.g. a fixed radius in AU) would no longer make sense.
        self._set_body_size_vars(default_sizes(3))
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
            model_state = state_from_inputs(
                p,
                body_names=[var.get().strip() or f"Body {i + 1}" for i, var in enumerate(self.body_name_vars)],
                body_colors=self.body_colors,
                units=self.units_var.get(),
                integrator_method=self.integrator_var.get(),
                adaptive=bool(self.adaptive_var.get()),
                body_sizes=self._current_body_sizes(strict=True),
            )
            self.controller.apply_state(model_state)
            engine = self.simulation_service.engine
            if engine is None:  # Defensive: reset() must always create an engine.
                raise RuntimeError("Simulation service did not create a physics engine.")
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
        if isinstance(self.system_metadata, dict):
            self.system_metadata["names"] = [v.get().strip() or f"Body {i + 1}" for i, v in enumerate(self.body_name_vars)]
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
        self._closest_approach = {}
        self._update_graphs()
        self.scene.display_scale = self.display_scale_var.get()
        self._apply_body_sizes(render=False)
        self.scene.set_view_mode(self.view_mode_var.get())
        self.scene.view_halfwidth = self.fixed_view
        self.scene.threshold = self.threshold
        self.scene.zone_mode = self.zone_mode_var.get()
        self.scene.set_display_options(display_scale=self.display_scale_var.get(),
                                       show_shells=self.shells_var.get(), show_field=self.field_var.get(),
                                       show_trails=self.trail_var.get(), show_floor=self.floor_var.get(),
                                       show_acceleration=self.accel_var.get(), show_axes=self.axes_var.get(), zone_mode=self.zone_mode_var.get(),
                                       threshold=self.threshold)
        self._refresh_camera_choices()
        display_frame = self._display_frame()
        self.scene.reset_trails(display_frame.pos, self.trail_count)
        self.scene.fit_camera(display_frame, view_halfwidth=self.fixed_view, include_shells=self.shells_var.get())
        self.scene.update(display_frame, force_field=True)
        self._camera_follow_position = None
        self._update_metrics()
        self._last_event_seen = len(self.engine.events)
        self._last_event_signature = self.engine.events[-1] if self.engine.events else None
        overlaps = overlap_warnings([b.name for b in model_state.bodies], [b.radius for b in model_state.bodies],
                                    [b.position for b in model_state.bodies])
        self.event_var.set("Warning: " + overlaps[0] if overlaps else "No events yet.")
        self._refresh_event_log()
        # A newly created or reset system must remain paused until the user presses Play.
        self.running = False
        self._timeline = []
        self._timeline_index = 0
        self._record_timeline_state(force=True)
        self._dirty = False
        self._render_once(force_field=True)
        self._update_status()

    def _update_metrics(self):
        if self.engine is None:
            return
        astro = self.units_var.get() == ASTRO
        for i in range(3):
            if not self.engine.alive[i]:
                name = self.body_name_vars[i].get().strip() or f"Body {i + 1}"
                self.metric_vars[i].set(f"{name} inactive — merged or removed")
                continue
            try:
                g, vesc, rho = self.engine.surface_properties(i)
            except (ValueError, ArithmeticError, FloatingPointError):
                self.metric_vars[i].set("Surface properties unavailable")
                continue
            if astro:
                g_si = g * AU_M / YEAR_S**2
                v_kms = vesc * AU_M / YEAR_S / 1000.0
                rho_si = rho * MSUN_KG / AU_M**3
                self.metric_vars[i].set(
                    f"g={format_finite(g_si, '.4g')} m/s²  |  vesc={format_finite(v_kms, '.4g')} km/s  |  ρ={format_finite(rho_si, '.4g')} kg/m³")
            else:
                self.metric_vars[i].set(
                    f"g={format_finite(g, '.4g')} L/T²  |  vesc={format_finite(vesc, '.4g')} L/T  |  ρ={format_finite(rho, '.4g')} M/L³")

    def _schedule_tick(self):
        if self._closed:
            return
        self._tick_after_id = self.root.after(16 if self.running else 80, self._tick)

    def _tick(self):
        self._tick_after_id = None
        if self._closed or self.engine is None:
            return
        self._frame += 1
        needs_scene_update = self.running or self._dirty
        if self.running and not self.failed:
            # Scale the time step, not the integer step count, so the speed slider
            # remains effective below 0.5x instead of rounding to one full step.
            self.controller.advance(
                steps=self.steps,
                dt=self.dt * self.speed_var.get(),
                method=self.integrator_var.get(),
                adaptive=self.adaptive_var.get(),
                max_wall=0.010,
            )
            # Renderer/history still consume the engine during the migration;
            # ownership and state transitions now live in SimulationService.
            self.engine = self.simulation_service.engine
            if self.engine is None:
                self.running = False
                self.status_var.set("Simulation service has no active engine. Reset to continue.")
                self._schedule_tick()
                return
            display_frame = self._display_frame()
            self.scene.push_positions(display_frame.pos, self.engine.alive)
            self.history.push(self.engine)
            self._record_timeline_state()
            if self.engine.events and (len(self.engine.events) > self._last_event_seen
                                        or self.engine.events[-1] != self._last_event_signature):
                self.event_var.set(self._friendly_event(self.engine.events[-1][1]))
                self._last_event_seen = len(self.engine.events)
                self._last_event_signature = self.engine.events[-1]
                self._refresh_event_log()
                self._update_metrics()
                self._update_graphs()
            if self.engine.impact:
                self.running = False
                self.event_var.set(self._friendly_event(self.engine.events[-1][1]) if self.engine.events else "Impact detected.")
                self._update_metrics()
                self._refresh_event_log()
                self._update_graphs()
            if not self.engine.is_healthy():
                self.failed = True
                self.running = False
                self.status_var.set("Numerical instability detected. Reduce Δt or enable adaptive stepping, then reset.")
            if (self.autozoom_var.get() and self._selected_body_index(self.camera_focus_var.get()) is None
                    and self.engine.is_healthy() and np.any(self.engine.alive)
                    and self._frame - self._last_fit_frame > 50):
                live_pos = self.engine.pos[self.engine.alive]
                if len(live_pos):
                    pos_extent = float(np.max(np.abs(live_pos - self.engine.center_of_mass())))
                    if math.isfinite(pos_extent) and pos_extent > self.scene.view_halfwidth * 0.94:
                        self.scene.fit_camera(self.simulation_service.render_frame(), view_halfwidth=max(self.scene.view_halfwidth, pos_extent * 1.3),
                                              include_shells=self.shells_var.get())
                        self._last_fit_frame = self._frame
            if self._frame - self._last_metric_update > 15:
                self._update_metrics()
                self._last_metric_update = self._frame
            if self._frame % 6 == 0:
                self._update_graphs()
            self._update_status()
        if needs_scene_update:
            self.scene.update(self._display_frame(), force_field=self._dirty)
            self._follow_camera_target()
            self.scene.render()
            self._dirty = False
        self._schedule_tick()

    def _update_graphs(self):
        time_values = list(self.history.t)
        names = [v.get().strip() or f"Body {i + 1}" for i, v in enumerate(self.body_name_vars)]
        event_times = [float(t) for t, _message in self.engine.events] if self.engine is not None else []
        unit_t = "yr" if self.units_var.get() == ASTRO else "model time"
        self.separation_graph.set_data(
            [list(x) for x in self.history.separations],
            labels=(f"{names[0]}–{names[1]}", f"{names[0]}–{names[2]}", f"{names[1]}–{names[2]}"),
            x_values=time_values, x_label=f"Time ({unit_t})", y_label="Separation", event_times=event_times)
        self.energy_graph.set_data(
            [list(self.history.energy_error)], labels=("|ΔE/E₀|",), logarithmic=True,
            x_values=time_values, x_label=f"Time ({unit_t})", y_label="Relative error (log₁₀)", event_times=event_times)
        self.momentum_graph.set_data(
            [list(self.history.momentum_error)], labels=("ΔP/P₀",), logarithmic=True,
            x_values=time_values, x_label=f"Time ({unit_t})", y_label="Relative error (log₁₀)", event_times=event_times)
        self.angular_momentum_graph.set_data(
            [list(self.history.angular_momentum_error)], labels=("ΔL/L₀",), logarithmic=True,
            x_values=time_values, x_label=f"Time ({unit_t})", y_label="Relative error (log₁₀)", event_times=event_times)

    def _friendly_event(self, message: str) -> str:
        """Replace generic engine body indexes with user-defined body names."""
        names = [v.get().strip() or f"Body {i + 1}" for i, v in enumerate(self.body_name_vars)]
        return re.sub(r"Body ([1-3])", lambda match: names[int(match.group(1)) - 1], str(message))

    def _refresh_event_log(self):
        if not hasattr(self, "event_text"):
            return
        events = list(self.engine.events) if self.engine is not None else []
        current_count = len(events)
        signature = (current_count, events[-1] if events else None)
        if signature == self._event_log_rendered_count:
            return
        unit_t = "yr" if self.units_var.get() == ASTRO else "T"
        self.event_text.configure(state=tk.NORMAL)
        self.event_text.delete("1.0", tk.END)
        if not events:
            self.event_text.insert(tk.END, "No collision or impact events recorded in this run.\n")
        else:
            for event_time, message in events[-150:]:
                self.event_text.insert(tk.END, f"t = {format_finite(event_time, '.7g')} {unit_t}  ·  {self._friendly_event(message)}\n")
        self.event_text.configure(state=tk.DISABLED)
        self.event_text.see(tk.END)
        self._event_log_rendered_count = signature

    def _update_status(self):
        if self.engine is None:
            return
        min_sep = minimum_active_pair_separation(self.engine.pos, self.engine.alive)
        min_sep_text = format_finite(min_sep, ".4g") if min_sep is not None else "N/A (fewer than two valid active bodies)"
        active_count = int(np.count_nonzero(self.engine.alive))
        unit_t = "yr" if self.units_var.get() == ASTRO else "T"
        self.timeline_label_var.set(f"t = {format_finite(self.engine.t, '.8g')} {unit_t}  ·  {self._timeline_index + 1}/{max(1, len(self._timeline))}")
        state = ("STOPPED: numerical issue — reduce Δt or tighten validation, then reset" if self.failed
                 else ("RUNNING" if self.running else ("IMPACT PAUSE" if self.engine.impact else "PAUSED")))
        energy = format_finite(self.engine.energy_error())
        angmom = format_finite(self.engine.angular_momentum_error())
        momentum = format_finite(self.engine.momentum_error())
        rk_note = ""
        if self.integrator_var.get() == RK45:
            rk_note = (f"   | RK45 local error = {format_finite(self.engine.rk45_last_error, '.1e')}"
                       f"   | accepted/rejected = {self.engine.rk45_accepted_steps}/{self.engine.rk45_rejected_steps}")
        active_physics = []
        if self.engine.enable_oblateness and np.any(np.abs(self.engine.j2) > 0): active_physics.append("J2")
        if self.engine.enable_1pn: active_physics.append("1PN(pairwise)")
        if self.engine.tidal_damping > 0: active_physics.append("tides(radial)")
        if np.any(np.linalg.norm(self.engine.spin_omega, axis=1) > 0): active_physics.append("body spin")
        ext_note = ("   |   " + "+".join(active_physics)) if active_physics else "   |   Newtonian"
        if self.engine.tidal_damping > 0:
            ext_note += f"   |   tidal heat = {format_finite(self.engine.tidal_energy_dissipated, '.3e')}"
        if self.engine.enable_1pn:
            ext_note += "   |   energy diagnostic omits 1PN Hamiltonian"
        if self.engine.enable_oblateness and np.any(np.abs(self.engine.j2) > 0):
            ext_note += "   |   J2 spin-axis reaction torque omitted"
        names = self._body_names_for_camera()
        distance_unit = "AU" if self.units_var.get() == ASTRO else "L"
        velocity_unit = "AU/yr" if self.units_var.get() == ASTRO else "L/T"
        relative_lines = []
        metrics = pairwise_relative_metrics(self.engine.pos, self.engine.vel, self.engine.alive)
        for pair, (distance, relative_speed) in metrics.items():
            prior = self._closest_approach.get(pair)
            if prior is None or distance < prior[0]:
                self._closest_approach[pair] = (distance, float(self.engine.t))
            closest, closest_time = self._closest_approach[pair]
            relative_lines.append(
                f"{names[pair[0]]}–{names[pair[1]]}: r={format_finite(distance, '.4g')} {distance_unit}, "
                f"v_rel={format_finite(relative_speed, '.4g')} {velocity_unit}, "
                f"closest={format_finite(closest, '.4g')} @ t={format_finite(closest_time, '.4g')} {unit_t}")
        frame_name = self.reference_frame_var.get()
        relative_summary = "\nRelative motion — " + (" | ".join(relative_lines) if relative_lines else "no active body pairs")
        self.status_var.set(
            f"{state} [{self.view_mode_var.get()}]  ·  t = {format_finite(self.engine.t, '.5g')} {unit_t}  ·  active bodies = {active_count}/3\n"
            f"|ΔE/E₀| = {energy}  ·  |ΔL/L₀| = {angmom}  ·  ΔP/P₀ = {momentum}  ·  minimum separation = {min_sep_text}{rk_note}\n"
            f"Frame: {frame_name}  ·  Collision mode: {self.collision_var.get()}  ·  {ext_note}"
            f"{relative_summary}")

    def _body_names_for_camera(self):
        return [v.get().strip() or f"Body {i + 1}" for i, v in enumerate(self.body_name_vars)]

    def _selected_body_index(self, value):
        if value in ("System center", "Inertial frame", "Barycentric frame"):
            return None
        names = self._body_names_for_camera()
        try:
            return names.index(value)
        except ValueError:
            return None

    def _refresh_camera_choices(self):
        if not hasattr(self, "camera_focus_combo"):
            return
        names = self._body_names_for_camera()
        focus_values = ["System center", *names]
        reference_values = ["Inertial frame", "Barycentric frame", *names]
        self.camera_focus_combo.configure(values=focus_values)
        self.reference_frame_combo.configure(values=reference_values)
        if self.camera_focus_var.get() not in focus_values:
            self.camera_focus_var.set("System center")
        if self.reference_frame_var.get() not in reference_values:
            self.reference_frame_var.set("Inertial frame")

    def _display_frame(self):
        """Return an immutable render frame expressed in the chosen body frame."""
        frame = self.simulation_service.render_frame()
        selected = self.reference_frame_var.get()
        acceleration = np.asarray(frame.accelerations())
        if selected == "Barycentric frame":
            pos, vel, acc = barycentric_frame(frame.pos, frame.vel, frame.m, frame.alive, acceleration)
            return replace(frame, pos=pos, vel=vel, _acceleration=acc)
        index = self._selected_body_index(selected)
        if index is None or not frame.alive[index]:
            return frame
        origin = np.asarray(frame.pos[index], dtype=float).copy()
        origin_velocity = np.asarray(frame.vel[index], dtype=float).copy()
        return replace(frame, pos=np.asarray(frame.pos) - origin,
                       vel=np.asarray(frame.vel) - origin_velocity,
                       _acceleration=acceleration - acceleration[index])

    def _on_camera_focus_changed(self, _event=None):
        self._camera_follow_position = None
        self._dirty = True
        self._render_once(force_field=True)

    def _on_reference_frame_changed(self, _event=None):
        if self.engine is None:
            return
        self._camera_follow_position = None
        frame = self._display_frame()
        self.scene.reset_trails(frame.pos, self.trail_count)
        self.scene.fit_camera(frame, view_halfwidth=self.fixed_view,
                              include_shells=self.shells_var.get())
        self._dirty = True
        self._render_once(force_field=True)

    def _follow_camera_target(self):
        """Lock the camera rig to the focused body's displayed world position.

        The camera and focal point are translated by the body's displacement,
        rather than resetting the focal point every frame.  This preserves the
        user's orbit angle and any cursor-zoom/pan offset while following motion.
        """
        if self.engine is None:
            return
        index = self._selected_body_index(self.camera_focus_var.get())
        if index is None or not self.engine.alive[index]:
            self._camera_follow_position = None
            return
        # Must use the exact coordinates that were sent to the renderer. This
        # also handles a selected reference frame and any future render offsets.
        display_frame = self._display_frame()
        target = np.asarray(display_frame.pos[index], dtype=float).copy()
        camera = self.scene.renderer.GetActiveCamera()
        delta = follow_translation(target, self._camera_follow_position, camera.GetFocalPoint())
        if np.any(np.abs(delta) > 0):
            position = np.asarray(camera.GetPosition(), dtype=float)
            focal = np.asarray(camera.GetFocalPoint(), dtype=float)
            camera.SetPosition(*(position + delta))
            camera.SetFocalPoint(*(focal + delta))
        self._camera_follow_position = target if np.all(np.isfinite(target)) else None

    def _recenter_camera(self):
        """Remove any pan/cursor-zoom offset: centre on the focused body (or the origin).

        Keeps the orbit angle and zoom level, so it is a gentle "snap back"
        rather than a full Fit view.
        """
        if self.engine is None or not hasattr(self, "scene"):
            return
        index = self._selected_body_index(self.camera_focus_var.get())
        target = np.zeros(3)
        if index is not None and self.engine.alive[index]:
            target = np.asarray(self._display_frame().pos[index], dtype=float)
        camera = self.scene.renderer.GetActiveCamera()
        position, focal = recentre(camera.GetPosition(), camera.GetFocalPoint(), target)
        camera.SetPosition(*position)
        camera.SetFocalPoint(*focal)
        self._camera_follow_position = target.copy() if index is not None else None
        self.scene.renderer.ResetCameraClippingRange()
        self._dirty = True
        self._render_once()

    def _render_once(self, force_field=False):
        if self.engine is None or not hasattr(self, "scene"):
            return
        self._refresh_camera_choices()
        self.scene.update(self._display_frame(), force_field=force_field)
        self._follow_camera_target()
        self.scene.render()
        self._dirty = False

    def _toggle_running(self):
        if self.failed:
            return
        if not self.running and self._timeline and self._timeline_index < len(self._timeline) - 1:
            # Branching from a rewound state discards the old future.
            self._timeline = self._timeline[:self._timeline_index + 1]
            self._update_timeline_widget()
        self.running = not self.running
        if self.engine and self.engine.impact and self.running:
            self.engine.impact = False
        self._update_status()

    def _record_timeline_state(self, force=False):
        """Keep bounded deep copies of complete engine states for deterministic rewind."""
        if self.engine is None:
            return
        if not force and self._timeline and abs(float(self._timeline[-1].t) - float(self.engine.t)) <= 1e-15:
            return
        self._timeline.append(copy.deepcopy(self.engine))
        if len(self._timeline) > self._timeline_maxlen:
            self._timeline.pop(0)
        self._timeline_index = len(self._timeline) - 1
        self._update_timeline_widget()

    def _update_timeline_widget(self):
        if not hasattr(self, "timeline_scale"):
            return
        self._timeline_updating = True
        try:
            maximum = max(0, len(self._timeline) - 1)
            self.timeline_scale.configure(from_=0, to=maximum)
            self.timeline_var.set(float(self._timeline_index))
            if self.engine is not None:
                unit_t = "yr" if self.units_var.get() == ASTRO else "T"
                self.timeline_label_var.set(f"t = {format_finite(self.engine.t, '.8g')} {unit_t}  ·  {self._timeline_index + 1}/{max(1, len(self._timeline))}")
        finally:
            self._timeline_updating = False

    def _restore_timeline_index(self, index):
        if not self._timeline:
            return
        index = max(0, min(len(self._timeline) - 1, int(round(index))))
        self.running = False
        self._timeline_index = index
        self.engine = copy.deepcopy(self._timeline[index])
        self.simulation_service.restore_engine(self.engine)
        self.engine = self.simulation_service.engine
        self.failed = not self.engine.is_healthy()
        self.history = History(maxlen=2200)
        self.history.push(self.engine)
        self._closest_approach = {}
        self.scene.reset_trails(self._display_frame().pos, self.trail_count)
        self.scene.update(self._display_frame(), force_field=True)
        self._update_metrics()
        self._refresh_event_log()
        self._update_graphs()
        self._update_timeline_widget()
        self._dirty = True
        self._render_once(force_field=True)
        self._update_status()

    def _on_timeline_seek(self, value):
        if self._timeline_updating or not self._timeline:
            return
        index = int(round(float(value)))
        if index != self._timeline_index:
            self._restore_timeline_index(index)

    def _step_backward(self):
        self._restore_timeline_index(self._timeline_index - 1)

    def _step_forward(self):
        if self.running:
            return
        if self._timeline_index < len(self._timeline) - 1:
            self._restore_timeline_index(self._timeline_index + 1)
        elif self.engine is not None and not self.failed:
            self.controller.advance(steps=1, dt=self.dt, method=self.integrator_var.get(),
                                    adaptive=self.adaptive_var.get(), max_wall=0.05)
            self.engine = self.simulation_service.engine
            self.history.push(self.engine)
            self._record_timeline_state(force=True)
            self.scene.push_positions(self._display_frame().pos, self.engine.alive)
            self._render_once()
            self._update_graphs()
            self._update_status()

    def _fit_camera(self):
        if self.engine is not None:
            self.scene.fit_camera(self._display_frame(), view_halfwidth=self._safe_float(self.view_var.get(), self.fixed_view),
                                  include_shells=self.shells_var.get())
            self._camera_follow_position = None
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
        headers = ["time", "separation_1_2", "separation_1_3", "separation_2_3",
                   "energy_error", "momentum_error", "angular_momentum_error"]
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
                    row = [t, *seps, self.history.energy_error[idx], self.history.momentum_error[idx],
                           self.history.angular_momentum_error[idx]]
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
        elif event.keysym.lower() == "f":
            self._fit_camera()
        elif event.keysym.lower() == "c":
            self._recenter_camera()

    def _close(self):
        self._closed = True
        if self._tick_after_id is not None:
            try:
                self.root.after_cancel(self._tick_after_id)
            except tk.TclError:
                pass
            self._tick_after_id = None
        try:
            self._save_user_preferences()
        except (OSError, ValueError, tk.TclError):
            # Preference persistence must never prevent the user from closing the app.
            pass
        try:
            self.vtk_interactor.Disable()
        except Exception:
            pass
        try:
            self.vtk_render_window.Finalize()
        except Exception:
            pass
        self.root.destroy()
