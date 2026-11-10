"""Launch start.bat headless, poll /api/health on 8000 then 8010, print it, always stop the server.

Exit 0 only when status is "ok". Set DADA_PYTHON to pick the interpreter start.bat uses.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORTS = (8000, 8010)


def fetch(port: int) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None


def listening_pids(port: int) -> set[int]:
    out = subprocess.run(["netstat", "-ano", "-p", "tcp"], check=False, capture_output=True, text=True).stdout
    pids: set[int] = set()
    for line in out.splitlines():
        m = re.search(rf"127\.0\.0\.1:{port}\s+\S+\s+LISTENING\s+(\d+)", line)
        if m:
            pids.add(int(m.group(1)))
    return pids


def kill(pid: int) -> None:
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], check=False, capture_output=True)


def main() -> int:
    env = dict(os.environ, NOPAUSE="1", NOBROWSER="1")
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    proc = subprocess.Popen(
        ["cmd", "/c", r".\start.bat"],
        cwd=ROOT,
        env=env,
        creationflags=flags,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    health: dict | None = None
    used: int | None = None
    try:
        deadline = time.time() + 60
        while time.time() < deadline and health is None:
            for port in PORTS:
                health = fetch(port)
                if health is not None:
                    used = port
                    break
            else:
                time.sleep(1)
        if health is None:
            print("serve check FAILED: no health answer on 8000 or 8010 within 60 s")
            return 1
        print(json.dumps(health, indent=2, ensure_ascii=False))
        return 0 if health.get("status") == "ok" else 1
    finally:
        kill(proc.pid)
        if used is not None:
            for pid in listening_pids(used):
                kill(pid)


if __name__ == "__main__":
    sys.exit(main())
