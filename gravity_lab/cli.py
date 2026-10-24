"""Command-line entry points for Gravity Lab 3D."""
from __future__ import annotations

import argparse


def main() -> None:
    """Launch the desktop GUI."""
    import tkinter as tk
    from .ui.main_window import GravityLabApp
    root = tk.Tk()
    GravityLabApp(root)
    root.mainloop()


def selftest_main() -> None:
    """Run the built-in physics self-checks."""
    from .selftest import run_selftest
    raise SystemExit(run_selftest())
