"""Regression tests for finite diagnostics and post-collision edge cases."""
import math

import numpy as np

from gravity_lab.ui.diagnostics_panel import format_finite, minimum_active_pair_separation


def test_format_finite_never_displays_nan_or_infinity():
    assert format_finite(0.125, ".3g") == "0.125"
    assert format_finite(float("nan")) == "N/A"
    assert format_finite(float("inf")) == "N/A"
    assert format_finite("not a number") == "N/A"
    assert format_finite(None, unavailable="Unavailable") == "Unavailable"


def test_minimum_separation_uses_only_active_pairs():
    positions = np.array([[0.0, 0.0, 0.0], [3.0, 0.0, 0.0], [0.0, 4.0, 0.0]])
    assert minimum_active_pair_separation(positions, [True, True, True]) == 3.0
    assert minimum_active_pair_separation(positions, [True, False, True]) == 4.0


def test_minimum_separation_reports_no_pair_after_merger():
    positions = np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [4.0, 0.0, 0.0]])
    assert minimum_active_pair_separation(positions, [True, False, False]) is None
    assert minimum_active_pair_separation(positions, [True, True, False]) == 0.0


def test_minimum_separation_handles_nonfinite_positions_and_bad_shape():
    positions = np.array([[0.0, 0.0, 0.0], [math.nan, 0.0, 0.0], [math.inf, 0.0, 0.0]])
    assert minimum_active_pair_separation(positions, [True, True, True]) is None
    assert minimum_active_pair_separation([[0, 0], [1, 1]], [True, True]) is None
