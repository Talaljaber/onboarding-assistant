import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "make_release.py"


def _run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, cwd=ROOT)


def test_dry_run_lists_and_excludes():
    r = _run("--dry-run")
    assert r.returncode == 0, r.stderr
    lines = set(r.stdout.splitlines())
    for want in ("app/main.py", "start.bat", "models/e5/model_int8.onnx"):
        assert want in lines
    for line in lines:
        parts = line.split("/")
        assert ".venv" not in parts and "node_modules" not in parts
        assert parts[-1] != ".env"


def test_real_build(tmp_path):
    r = _run("--allow-dirty", "--out", str(tmp_path))
    assert r.returncode == 0, r.stderr
    assert "sha256:" in r.stdout
    z = next(tmp_path.glob("onboarding-assistant-*.zip"))
    with zipfile.ZipFile(z) as zf:
        names = {n.split("/", 1)[1]: n for n in zf.namelist()}
        assert b"\r\n" in zf.read(names["start.bat"])
        for csv in (ROOT / "data" / "official").glob("*.csv"):
            assert zf.read(names[f"data/official/{csv.name}"]) == csv.read_bytes()
        assert not any(n.endswith("/.env") or "node_modules/" in n for n in names)
