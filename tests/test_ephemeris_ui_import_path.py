"""Regression guard for the lazy Horizons imports in the extracted UI package."""
import ast
from pathlib import Path


def test_horizons_imports_resolve_from_parent_package():
    source = Path(__file__).parents[1] / "gravity_lab" / "ui" / "main_window.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imports = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "ephemeris"
    ]
    assert len(imports) == 2
    assert all(node.level == 2 for node in imports)
