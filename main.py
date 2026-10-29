"""Launch Gravity Lab 3D.

Examples:
  python main.py
  python main.py --selftest
  python main.py --list-presets
  python main.py --snapshot preview.png --preset "Sun - Earth - Jupiter (astronomical)" --time 2 --view-mode 2D
"""
from __future__ import annotations
import argparse
import math
import platform
import sys

# Apply Windows DPI awareness before any Tkinter import or Tk window creation.
if platform.system() == "Windows":
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


def build_parser():
    p = argparse.ArgumentParser(description="Interactive 3D Newtonian three-body gravity simulator")
    p.add_argument("--selftest", action="store_true", help="run numerical physics checks and exit")
    p.add_argument("--list-presets", action="store_true", help="print all system presets and exit")
    p.add_argument("--snapshot", metavar="PATH", help="render a headless PNG snapshot to PATH")
    p.add_argument("--preset", default="3D inclined triple (recommended)", help="system preset for --snapshot")
    p.add_argument("--time", type=float, default=0.0, help="advance simulation to this time before snapshot")
    p.add_argument("--theme", default="Dark", choices=("Light", "Dark", "System"),
                   help="theme for --snapshot (System follows the operating system setting)")
    p.add_argument("--width", type=int, default=1500, help="snapshot width in pixels")
    p.add_argument("--height", type=int, default=950, help="snapshot height in pixels")
    p.add_argument("--view-mode", choices=("2D", "3D"), default="3D", help="snapshot camera mode (2D XY or 3D)")
    return p


def _configure_output_encoding():
    """Keep printing from crashing on narrow consoles/pipes (e.g. Windows cp1252 in CI).

    The self-test and CLI print symbols such as ε, ² and —. Redirected output is
    switched to UTF-8; interactive consoles keep their encoding and only get a safe error
    handler, so nothing can raise UnicodeEncodeError.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream.isatty():
                stream.reconfigure(errors="replace")
            else:
                stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass  # replaced/closed streams (some IDEs, pytest capture) are left alone


def main(argv=None):
    _configure_output_encoding()
    args = build_parser().parse_args(argv)
    if args.selftest:
        from gravity_lab.selftest import run_selftest
        return run_selftest()
    if args.list_presets:
        from gravity_lab.presets import PRESET_NAMES
        print("Available presets:")
        for name in PRESET_NAMES:
            print(f"  - {name}")
        return 0
    if args.snapshot:
        from gravity_lab.presets import PRESETS, engine_inputs
        from gravity_lab.physics import ThreeBodyEngine, PASS, YOSHIDA
        from gravity_lab.renderer_vtk import GravityScene
        from gravity_lab.system_theme import detect_system_theme
        from gravity_lab.themes import resolve_theme
        import vtk
        if args.preset not in PRESETS:
            print(f"Unknown preset {args.preset!r}. Use --list-presets to inspect names.", file=sys.stderr)
            return 2
        if not math.isfinite(args.time) or args.time < 0:
            print("--time must be a finite non-negative number.", file=sys.stderr)
            return 2
        p = PRESETS[args.preset]
        m, r, pos, vel = engine_inputs(p)
        # Use the preset's physical collision model where available. With exact
        # Newtonian gravity, preventing contact tunneling is preferable to
        # letting finite-radius bodies pass through one another by default.
        engine = ThreeBodyEngine(m, r, pos, vel, p["G"], p["soft"], collision=p.get("collision", PASS))
        target = float(args.time)
        # Fixed stepping is deterministic for snapshots and remains independent of Tk.
        dt = min(float(p["dt"]), max(target / 4000.0, 1e-5)) if target else float(p["dt"])
        method = p.get("integrator", YOSHIDA)
        # Keep a bounded, evenly sampled path history so headless screenshots show
        # the trajectory up to the requested time rather than a single final dot.
        estimated_steps = max(1, int(math.ceil(target / max(dt, 1e-15)))) if target else 1
        stride = max(1, int(math.ceil(estimated_steps / 1200.0)))
        path_positions = [engine.pos.copy()]
        path_alive = [engine.alive.copy()]
        step_index = 0
        while engine.t < target - 1e-12:
            engine.step(min(dt, target - engine.t), method)
            step_index += 1
            if step_index % stride == 0 or engine.t >= target - 1e-12:
                path_positions.append(engine.pos.copy())
                path_alive.append(engine.alive.copy())
        window = vtk.vtkRenderWindow()
        window.SetSize(max(320, args.width), max(240, args.height))
        window.SetOffScreenRendering(1)
        scene = GravityScene(window, theme=resolve_theme(
            args.theme, detect_system_theme() if args.theme == "System" else None))
        scene.set_view_mode(args.view_mode)
        display_scale = float(p.get("display_scale", 1.8))
        show_shells = bool(p.get("show_shells", True))
        show_field = bool(p.get("show_field", True))
        show_trails = bool(p.get("show_trails", True))
        show_floor = bool(p.get("show_floor", True))
        scene.view_halfwidth = float(p["view"])
        scene.threshold = float(p["threshold"])
        scene.set_display_options(display_scale=display_scale, show_shells=show_shells,
                                  show_field=show_field, show_trails=show_trails,
                                  show_floor=show_floor, threshold=scene.threshold)
        scene.reset_trails(path_positions[0], max(10, min(1200, len(path_positions) + 1)))
        for path_pos, path_live in zip(path_positions[1:], path_alive[1:]):
            scene.push_positions(path_pos, path_live)
        scene.fit_camera(engine, view_halfwidth=float(p["view"]), include_shells=show_shells)
        scene.update(engine, force_field=show_field)
        scene.render()
        scene.save_png(args.snapshot)
        window.Finalize()
        print(f"Saved {args.snapshot} at t={engine.t:.6g} ({args.preset})")
        return 0
    try:
        import tkinter as tk
        from gravity_lab.ui.main_window import GravityLabApp
    except Exception as exc:
        print("GUI startup failed. Install the requirements in requirements.txt.\n" + str(exc), file=sys.stderr)
        return 1
    root = tk.Tk()
    GravityLabApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
