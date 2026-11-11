"""Fixtures for the browser smoke test: a real uvicorn on port 8010 (or E2E_PORT), offline, with a temp live-data dir."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PORT = int(os.environ.get("E2E_PORT") or 8010)  # P14.1: E2E_PORT overrides the default for a busy machine
BASE = f"http://127.0.0.1:{PORT}"


def _port_busy(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _stop(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], check=False, capture_output=True)
    else:
        proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="session")
def server() -> Iterator[str]:
    if not (ROOT / "web" / "dist" / "index.html").exists():
        pytest.skip("web/dist is not built (npm run build --prefix web)")
    if _port_busy(PORT):
        pytest.fail(f"port {PORT} is already in use")
    with tempfile.TemporaryDirectory(prefix="dada-e2e-live-") as live:
        env = dict(os.environ, OFFLINE="1", STORE="local", OPENROUTER_API_KEY="", DATA_LIVE=live,
                   PYTHONIOENCODING="utf-8")
        env.pop("SUPABASE_URL", None)
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(PORT),
             "--log-level", "warning"],
            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    pytest.fail("the server exited before answering /api/health")
                try:
                    with urllib.request.urlopen(BASE + "/api/health", timeout=2):
                        break
                except OSError:
                    time.sleep(0.5)
            else:
                pytest.fail("the server did not answer /api/health within 90 s")
            yield BASE
        finally:
            _stop(proc)
