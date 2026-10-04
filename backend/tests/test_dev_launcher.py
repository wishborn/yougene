import importlib.util
import signal
import subprocess
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("dev", ROOT / "scripts/dev.py")
dev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dev)


def record_children(monkeypatch):
    children = []
    original = subprocess.Popen

    def spawn(*args, **kwargs):
        process = original(*args, **kwargs)
        if args[0][0] == sys.executable:
            children.append(process)
        return process

    monkeypatch.setattr(dev.subprocess, "Popen", spawn)
    return children


def test_launcher_stops_sibling_on_exit(monkeypatch, tmp_path):
    children = record_children(monkeypatch)
    code = dev.supervise(
        [
            (
                "api",
                [
                    sys.executable,
                    "-c",
                    "import time; time.sleep(0.3); raise SystemExit(3)",
                ],
            ),
            ("vite", [sys.executable, "-c", "import time; time.sleep(30)"]),
        ],
        tmp_path,
    )
    assert code == 3
    assert len(children) == 2 and all(child.poll() is not None for child in children)


@pytest.mark.parametrize("received", [signal.SIGINT, signal.SIGTERM])
def test_launcher_signal_cleanup(monkeypatch, tmp_path, received):
    children = record_children(monkeypatch)
    handlers = {}

    def register(number, handler):
        previous = handlers.get(number, signal.SIG_DFL)
        handlers[number] = handler
        return previous

    monkeypatch.setattr(dev.signal, "signal", register)
    timer = threading.Timer(0.4, lambda: handlers[received](received, None))
    timer.start()
    try:
        code = dev.supervise(
            [
                (label, [sys.executable, "-c", "import time; time.sleep(30)"])
                for label in ["api", "vite"]
            ],
            tmp_path,
        )
    finally:
        timer.cancel()
        timer.join()
    assert code == 0
    assert len(children) == 2 and all(child.poll() is not None for child in children)


def test_launcher_cleans_up_partial_start(monkeypatch, tmp_path):
    children = record_children(monkeypatch)
    with pytest.raises(FileNotFoundError):
        dev.supervise(
            [
                ("api", [sys.executable, "-c", "import time; time.sleep(30)"]),
                ("vite", [str(tmp_path / "missing-executable")]),
            ],
            tmp_path,
        )
    assert len(children) == 1 and children[0].poll() is not None
