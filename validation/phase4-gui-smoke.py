"""Minimal Tk/VTK startup, preferences-persistence and close smoke test."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tkinter as tk
from gravity_lab.ui.main_window import GravityLabApp

root = tk.Tk()
first = GravityLabApp(root)
first.theme_var.set("Midnight Dark")
first.view_mode_var.set("2D")
first.axes_var.set(False)
root.after(1200, first._close)
root.mainloop()

root2 = tk.Tk()
second = GravityLabApp(root2)
assert second.theme_var.get() == "Midnight Dark"
assert second.view_mode_var.get() == "2D"
assert second.axes_var.get() is False
root2.after(1200, second._close)
root2.mainloop()
print("GUI startup, UI preference persistence, and close smoke test passed")
