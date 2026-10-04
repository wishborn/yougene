"""Run both loopback dev servers as one Genie Site; stop together on failure."""

import os
import shutil
import signal
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def stop_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        # Kill the whole child tree; no orphan Vite/compiler subprocesses.
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            process.kill()
        else:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


def stream(label: str, process: subprocess.Popen) -> None:
    if process.stdout is not None:
        for line in process.stdout:
            print(f"[{label}] {line.rstrip()}", flush=True)


def supervise(commands: list[tuple[str, list[str]]], cwd: Path = ROOT) -> int:
    stopped = threading.Event()
    children: list[subprocess.Popen] = []
    threads: list[threading.Thread] = []
    previous = {}

    def on_signal(_number, _frame):
        stopped.set()

    for number in (signal.SIGINT, signal.SIGTERM):
        previous[number] = signal.signal(number, on_signal)
    try:
        for label, command in commands:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                start_new_session=os.name != "nt",
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                if os.name == "nt"
                else 0,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
            children.append(process)
            thread = threading.Thread(target=stream, args=(label, process), daemon=True)
            thread.start()
            threads.append(thread)
        while not stopped.wait(0.2):
            for (label, _), child in zip(commands, children, strict=True):
                code = child.poll()
                if code is not None:
                    print(
                        f"[dev] {label} exited ({code}); stopping both servers",
                        flush=True,
                    )
                    return code or 1
        return 0
    finally:
        for child in children:
            stop_process(child)
        for thread in threads:
            thread.join(timeout=2)
        for number, handler in previous.items():
            signal.signal(number, handler)


def main() -> int:
    # Genie allocates an upstream port for command sites and exports PORT.
    # Direct local runs retain the work order's 5180 fallback.
    port = int(os.environ.get("PORT", "5180"))
    if not 1 <= port <= 65535:
        raise ValueError("PORT must be between 1 and 65535")
    for handle in (sys.stdout, sys.stderr):
        if hasattr(handle, "reconfigure"):
            handle.reconfigure(encoding="utf-8", errors="replace")
    print(f"[dev] Vite loopback port {port}; API loopback port 8765", flush=True)
    python = (
        ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    )
    vite = ROOT / "frontend/node_modules/vite/bin/vite.js"
    node = shutil.which("node")
    if not python.is_file() or not vite.is_file() or node is None:
        print(
            "[dev] Install the repo venv/backend and frontend dependencies first.",
            file=sys.stderr,
        )
        return 1
    return supervise(
        [
            ("api", [str(python), "-m", "yougene.cli", "serve", "--port", "8765"]),
            (
                "vite",
                [
                    node,
                    str(vite),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--strictPort",
                ],
            ),
        ],
        cwd=ROOT / "frontend",
    )


if __name__ == "__main__":
    sys.exit(main())
