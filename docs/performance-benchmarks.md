# Phase 3 performance report

## Method

Generated with `python benchmarks/run_benchmarks.py --steps 200 --profile-iterations 1000`. Each case runs three times and reports median wall-clock duration. Compare results only on the same machine, Python/NumPy build, and system load. These are short microbenchmarks, not universal performance guarantees.

The baseline JSON was captured before the allocation-light Newtonian pair-accumulation path. The optimized JSON was captured after it. Both use the same preset names, step sizes, 200-step request and benchmark harness for the five comparable cases.

## Before / after

| Case | Baseline (ms) | Optimized (ms) | Faster by | Relative energy error before → after |
|---|---:|---:|---:|---|
| `periodic-verlet` | 4.005 | 2.916 | 27.2% | 6.452e-07 → 6.452e-07 |
| `periodic-yoshida` | 9.697 | 6.759 | 30.3% | 4.678e-12 → 4.678e-12 |
| `periodic-rk45` | 29.794 | 22.195 | 25.5% | 8.625e-16 → 8.625e-16 |
| `collision-free-yoshida` | 9.544 | 6.889 | 27.8% | 1.295e-15 → 1.295e-15 |
| `collision-mode-merge` | 15.601 | 14.292 | 8.4% | 1.742e-14 → 1.742e-14 |


## Interpretation

- The common Newtonian force path now accumulates the three active body pairs directly, avoiding broadcast arrays, distance matrices, and two `einsum` reductions for every acceleration evaluation.
- Across these local 200-step runs, the five cases were approximately 8–30% faster. The collision-handling case improved less than the collision-free cases because event handling and integration work remain a substantial portion of its cost.
- The reported relative energy errors match to the printed precision for all five comparable cases, and the physics self-check suite passes unchanged. The fast path is used only when J2, pairwise 1PN and tidal damping are disabled; advanced corrections continue through the original general implementation.
- The separate `tracemalloc` + `cProfile` run is useful for identifying allocation hotspots but has high instrumentation overhead. Do not interpret its elapsed time as normal simulation speed. Peak traced allocations for the acceleration micro-loop decreased from about 6.9 KB to about 3.3 KB in these runs, though this small figure is sensitive to interpreter and tracing details.
- A synthetic overlapping-start collision case was added to `optimized.json` to exercise the collision path. It is not compared to the baseline because it was added after the initial baseline capture.

## Reproduce

```bash
python benchmarks/run_benchmarks.py --steps 200 --profile-iterations 1000 --output benchmark-results/latest.json
python main.py --selftest
python -m pytest -q
```

The JSON report records the Python, platform, NumPy version and preset-catalog SHA-256. Timing varies by machine. Keep the numerical tests as the correctness gate; benchmark timing itself is not a flaky CI threshold.
