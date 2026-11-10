"""Clean-clone test: clone this repo, run start.bat under a scrubbed environment, check health.

Slow (creates a venv and installs packages). Use --dry-run to print the plan only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TARGET = Path(r"C:\Users\hp\.m2\dada-clean-test")
PORTS = (8000, 8010)
TIMEOUT_S = 1200  # first run installs packages


def scrubbed_env() -> dict[str, str]:
    path = [r"C:\Windows\System32", r"C:\Windows", r"C:\Windows\System32\WindowsPowerShell\v1.0"]
    py = shutil.which("py")
    if py:
        path.append(str(Path(py).parent))
    env = {
        "PATH": ";".join(path),
        "SystemRoot": os.environ.get("SystemRoot", r"C:\Windows"),
        "TEMP": os.environ.get("TEMP", r"C:\Windows\Temp"),
        "TMP": os.environ.get("TMP", r"C:\Windows\Temp"),
        "USERPROFILE": os.environ.get("USERPROFILE", ""),
        "LOCALAPPDATA": os.environ.get("LOCALAPPDATA", ""),
        "APPDATA": os.environ.get("APPDATA", ""),
        "PYTHONNOUSERSITE": "1",
        "NOPAUSE": "1",
        "NOBROWSER": "1",
    }
    return {k: v for k, v in env.items() if v}


def health(port: int) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None


def listening_pids(port: int) -> set[int]:
    out = subprocess.run(["netstat", "-ano", "-p", "tcp"], check=False, capture_output=True, text=True).stdout
    return {
        int(m.group(1))
        for line in out.splitlines()
        if (m := re.search(rf"127\.0\.0\.1:{port}\s+\S+\s+LISTENING\s+(\d+)", line))
    }


def kill(pid: int) -> None:
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], check=False, capture_output=True)


def _rm_readonly(func, path, _exc) -> None:  # type: ignore[no-untyped-def]
    os.chmod(path, stat.S_IWRITE)
    func(path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="print the plan and exit")
    args = ap.parse_args()
    if args.dry_run:
        print(f"would clone {REPO} into {TARGET}")
        print("would run: cmd /c start.bat with env:")
        for k, v in scrubbed_env().items():
            print(f"  {k}={v}")
        print(f"would poll /api/health on {PORTS} for up to {TIMEOUT_S} s, require mode offline,")
        print("then kill the server tree and delete the clone")
        return 0

    if TARGET.exists():
        shutil.rmtree(TARGET, onerror=_rm_readonly)
    subprocess.run(["git", "clone", "--quiet", str(REPO), str(TARGET)], check=True)
    proc: subprocess.Popen | None = None
    used: int | None = None
    code = 1
    try:
        proc = subprocess.Popen(
            ["cmd", "/c", r".\start.bat"],
            cwd=TARGET,
            env=scrubbed_env(),
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        got: dict | None = None
        deadline = time.time() + TIMEOUT_S
        while time.time() < deadline and got is None:
            for port in PORTS:
                got = health(port)
                if got is not None:
                    used = port
                    break
            else:
                time.sleep(2)
        if got is None:
            print("clean clone FAILED: no health answer")
        elif got.get("status") != "ok" or got.get("mode") != "offline":
            print(f"clean clone FAILED: health={got}")
        else:
            code = 0
    finally:
        if proc is not None:
            kill(proc.pid)
        if used is not None:
            for pid in listening_pids(used):
                kill(pid)
        time.sleep(2)
        shutil.rmtree(TARGET, onerror=_rm_readonly)
    if code == 0:
        print("clean clone: start.bat OK, health ok, mode=offline, cleanup done")
    return code


if __name__ == "__main__":
    sys.exit(main())
