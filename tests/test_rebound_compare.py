import importlib.util
import pytest

from gravity_lab.rebound_compare import compare_against_rebound


def test_rebound_comparison_has_clear_optional_dependency_error_when_missing():
    if importlib.util.find_spec("rebound") is not None:
        pytest.skip("REBOUND is installed; validate its actual backend separately")
    with pytest.raises(RuntimeError, match="pip install rebound"):
        compare_against_rebound([1, 1, 1], [0.1, 0.1, 0.1],
            [[-1, 0, 0], [1, 0, 0], [0, 3, 0]],
            [[0, -0.5, 0], [0, 0.5, 0], [0.2, 0, 0]], 1, 0.2)
