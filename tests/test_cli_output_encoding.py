"""The CLI must not crash when stdout cannot encode the symbols it prints (Windows CI, cp1252)."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class FakeStream:
    def __init__(self, tty):
        self.tty, self.calls = tty, []

    def isatty(self):
        return self.tty

    def reconfigure(self, **kwargs):
        self.calls.append(kwargs)

    def write(self, _text):
        return 0

    def flush(self):
        pass


def test_redirected_output_is_switched_to_utf8_and_consoles_keep_their_encoding(monkeypatch):
    import main

    piped, console = FakeStream(False), FakeStream(True)
    monkeypatch.setattr(sys, "stdout", piped)
    monkeypatch.setattr(sys, "stderr", console)
    main._configure_output_encoding()
    assert piped.calls == [{"encoding": "utf-8", "errors": "replace"}]
    assert console.calls == [{"errors": "replace"}]


def test_streams_without_reconfigure_are_left_alone(monkeypatch):
    import io
    import main

    monkeypatch.setattr(sys, "stdout", io.StringIO())
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    main._configure_output_encoding()  # must not raise


def test_cli_output_survives_a_cp1252_pipe():
    """Preset names contain symbols such as ≈ that cp1252 cannot encode (Windows CI pipes)."""
    env = dict(os.environ, PYTHONIOENCODING="cp1252", PYTHONUTF8="0")
    result = subprocess.run([sys.executable, str(ROOT / "main.py"), "--list-presets"],
                            env=env, capture_output=True, timeout=120)
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")[-500:]
    assert "\u2248" in result.stdout.decode("utf-8")
