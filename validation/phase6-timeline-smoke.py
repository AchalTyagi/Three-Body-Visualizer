"""Phase 6 startup-paused, step, rewind, and play-state smoke test."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tkinter as tk
from gravity_lab.ui.main_window import GravityLabApp

root = tk.Tk()
app = GravityLabApp(root)
root.update()
assert app.running is False, "The simulation must start paused."
assert len(app._timeline) == 1, "The initial state should be on the timeline."
initial_t = app.engine.t
app._step_forward()
root.update()
assert app.engine.t > initial_t, "Step + should advance simulation time once."
stepped_t = app.engine.t
app._step_backward()
root.update()
assert app.engine.t == initial_t, "Step − should restore the prior recorded state."
app._toggle_running()
assert app.running is True, "Play should explicitly start the simulation."
app._toggle_running()
assert app.running is False, "Pause should stop the simulation."
app._close()
print("Phase 6 startup-paused, step, rewind, and play-state smoke test passed")
