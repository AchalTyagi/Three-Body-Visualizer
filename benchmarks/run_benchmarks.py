"""Reproducible microbenchmarks for Gravity Lab 3D's three-body engine.

Run from the repository root: python benchmarks/run_benchmarks.py --steps 2000
The JSON report records Python/NumPy versions and a deterministic preset fingerprint.
Timings are descriptive, not pass/fail thresholds; compare on the same machine.
"""
from __future__ import annotations

import argparse
import cProfile
import hashlib
import json
import platform
import pstats
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gravity_lab.physics import ThreeBodyEngine, VERLET, YOSHIDA, RK45, PASS, MERGE, BOUNCE  # noqa: E402
from gravity_lab.presets import PRESETS, engine_inputs  # noqa: E402


def preset_fingerprint() -> str:
    payload = json.dumps(PRESETS, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def make_engine(preset_name: str, collision_override: str | None = None) -> ThreeBodyEngine:
    preset = PRESETS[preset_name]
    masses, radii, positions, velocities = engine_inputs(preset)
    return ThreeBodyEngine(
        masses, radii, positions, velocities, G=preset["G"], softening=preset["soft"],
        collision=collision_override or preset["collision"],
        rtol=1e-9, atol=1e-12,
    )


def run_case(name: str, preset_name: str, method: str, steps: int, collision: str | None = None) -> dict:
    durations = []
    final_time = 0.0
    final_energy_error = None
    for _ in range(3):
        engine = make_engine(preset_name, collision)
        start = time.perf_counter()
        for _step in range(steps):
            engine.step(float(PRESETS[preset_name]["dt"]), method)
            if engine.impact:
                break
        durations.append(time.perf_counter() - start)
        final_time = float(engine.t)
        value = float(engine.energy_error())
        final_energy_error = value if np.isfinite(value) else None
    return {
        "case": name, "preset": preset_name, "integrator": method,
        "requested_steps": steps, "elapsed_seconds_median": statistics.median(durations),
        "steps_per_second": steps / statistics.median(durations),
        "simulated_time": final_time, "relative_energy_error": final_energy_error,
        "collision_mode": collision or PRESETS[preset_name]["collision"],
    }


def run_collision_heavy_case(steps: int) -> dict:
    """Exercise the collision path with a deliberately overlapping start."""
    durations = []
    event_count = 0
    for _ in range(3):
        engine = ThreeBodyEngine(
            [1.0, 1.0, 0.25], [0.15, 0.15, 0.08],
            [[-0.12, 0.0, 0.0], [0.12, 0.0, 0.0], [0.0, 3.0, 0.0]],
            [[0.2, 0.0, 0.0], [-0.2, 0.0, 0.0], [0.0, 0.0, 0.0]],
            G=0.2, collision=BOUNCE,
        )
        start = time.perf_counter()
        for _step in range(steps):
            engine.step(0.001, YOSHIDA)
            if engine.impact:
                break
        durations.append(time.perf_counter() - start)
        event_count = len(engine.events)
    median = statistics.median(durations)
    return {"case": "collision-heavy-overlap-start", "preset": "synthetic-overlap-test",
            "integrator": YOSHIDA, "requested_steps": steps,
            "elapsed_seconds_median": median, "steps_per_second": steps / median,
            "simulated_time": float(engine.t), "relative_energy_error":
            float(engine.energy_error()) if np.isfinite(engine.energy_error()) else None,
            "collision_mode": BOUNCE, "collision_events": event_count}


def profile_acceleration(preset_name: str, iterations: int) -> dict:
    engine = make_engine(preset_name, PASS)
    profiler = cProfile.Profile()
    tracemalloc.start()
    start = time.perf_counter()
    profiler.enable()
    for _ in range(iterations):
        engine.accelerations()
    profiler.disable()
    elapsed = time.perf_counter() - start
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    from io import StringIO
    output = StringIO()
    pstats.Stats(profiler, stream=output).sort_stats("cumtime").print_stats(12)
    return {
        "iterations": iterations, "elapsed_seconds": elapsed,
        "calls_per_second": iterations / elapsed if elapsed else None,
        "tracemalloc_current_bytes": current, "tracemalloc_peak_bytes": peak,
        "top_functions": output.getvalue(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", type=int, default=1000)
    parser.add_argument("--profile-iterations", type=int, default=20000)
    parser.add_argument("--output", default="benchmark-results/latest.json")
    args = parser.parse_args()
    if args.steps < 1 or args.profile_iterations < 1:
        parser.error("steps and profile-iterations must be positive")

    periodic = next(name for name in PRESETS if "Figure-eight (classic" in name)
    stable = "Sun - Earth - Jupiter (astronomical)"
    cases = [
        run_case("periodic-verlet", periodic, VERLET, args.steps, PASS),
        run_case("periodic-yoshida", periodic, YOSHIDA, args.steps, PASS),
        run_case("periodic-rk45", periodic, RK45, args.steps, PASS),
        run_case("collision-free-yoshida", stable, YOSHIDA, args.steps, PASS),
        run_case("collision-mode-merge", "3D inclined triple (recommended)", YOSHIDA, args.steps, MERGE),
        run_collision_heavy_case(args.steps),
    ]
    report = {
        "schema_version": 1,
        "environment": {"python": platform.python_version(), "platform": platform.platform(), "numpy": np.__version__},
        "preset_sha256": preset_fingerprint(),
        "cases": cases,
        "acceleration_profile": profile_acceleration(periodic, args.profile_iterations),
        "notes": ["Three independent timing repetitions; median reported.",
                  "Benchmark times vary by hardware and background load.",
                  "Collision-mode case may terminate early if a collision occurs."],
    }
    target = ROOT / args.output
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(target), "cases": cases,
                      "acceleration_profile": {k: v for k, v in report["acceleration_profile"].items() if k != "top_functions"}}, indent=2))


if __name__ == "__main__":
    main()
