"""Build release/onboarding-assistant-<sha>.zip from the committed tree.

Usage: python scripts/make_release.py [--dry-run] [--allow-dirty] [--out DIR]
The archive is only written locally; nothing is sent anywhere.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_BYTES = 120 * 1024 * 1024
FORBIDDEN_DIRS = {".git", ".cache", "node_modules", "logs", "release", ".venv"}
FORBIDDEN_PREFIXES = ("data/live/",)
ENV_ALLOWED = {".env.example"}


def _git(root: Path, *args: str) -> bytes:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True).stdout


def is_forbidden(rel: str) -> bool:
    parts = rel.split("/")
    if any(p in FORBIDDEN_DIRS for p in parts[:-1]) or parts[0] in FORBIDDEN_DIRS:
        return True
    if rel.startswith(FORBIDDEN_PREFIXES):
        return True
    name = parts[-1]
    return (name == ".env" or name.startswith(".env.")) and name not in ENV_ALLOWED


def tracked_files(root: Path) -> list[str]:
    out = _git(root, "ls-files", "-z").decode("utf-8")
    return sorted(p for p in out.split("\0") if p)


def check_official(root: Path) -> None:
    sums = root / "data" / "official" / "SHA256SUMS.txt"
    for line in sums.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, name = line.split(None, 1)
        name = name.strip().lstrip("*")
        actual = hashlib.sha256((root / "data" / "official" / name).read_bytes()).hexdigest()
        if actual != digest.lower():
            raise SystemExit(f"official file hash mismatch: {name}")


def build(root: Path, out_dir: Path, sha: str, files: list[str]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"onboarding-assistant-{sha}.zip"
    prefix = f"onboarding-assistant-{sha}/"
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, strict_timestamps=False) as zf:
        for rel in files:
            zf.write(root / rel, prefix + rel)
    return dest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--allow-dirty", action="store_true")
    ap.add_argument("--out", type=Path, default=ROOT / "release")
    ap.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    root: Path = args.root

    sha = _git(root, "rev-parse", "--short", "HEAD").decode().strip()
    dirty = bool(_git(root, "status", "--porcelain").strip())
    if dirty and not args.allow_dirty and not args.dry_run:
        print("refusing to build from a dirty tree (use --allow-dirty)", file=sys.stderr)
        return 2

    files = [f for f in tracked_files(root) if (root / f).is_file()]
    bad = [f for f in files if is_forbidden(f)]
    if bad:
        print(f"refusing: forbidden tracked paths: {bad}", file=sys.stderr)
        return 2
    check_official(root)

    if args.dry_run:
        for f in files:
            print(f)
        print(f"[dry-run] {len(files)} files, would write onboarding-assistant-{sha}.zip")
        return 0

    dest = build(root, args.out, sha, files)
    size = dest.stat().st_size
    digest = hashlib.sha256(dest.read_bytes()).hexdigest()
    print(f"files: {len(files)}")
    print(f"size: {size / 1048576:.2f} MB")
    print(f"sha256: {digest}  {dest.name}")
    if size >= MAX_BYTES:
        print("FAIL: archive is 120 MB or larger", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
