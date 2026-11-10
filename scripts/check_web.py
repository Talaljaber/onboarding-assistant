"""Static checks on the web client: direction classes, secrets in dist, dist freshness.

Tolerates a missing web/src (placeholder phase). Exit 1 with a list on failure.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "web" / "src"
DIST = ROOT / "web" / "dist"
SRC_EXT = {".ts", ".tsx", ".js", ".jsx", ".css", ".html"}
PHYSICAL = re.compile(
    r"(?<![\w-])(?:-?(?:ml|mr|pl|pr|left|right)-[\w\[\]./%-]+|text-left|text-right)(?![\w-])"
)
SECRETS = ("sk-or-", "OPENROUTER", "api_key")


def newest_mtime(folder: Path) -> float:
    times = [p.stat().st_mtime for p in folder.rglob("*") if p.is_file()]
    return max(times, default=0.0)


def main() -> int:
    problems: list[str] = []
    if SRC.is_dir():
        for path in SRC.rglob("*"):
            if not path.is_file() or path.suffix not in SRC_EXT:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for n, line in enumerate(text.splitlines(), 1):
                m = PHYSICAL.search(line)
                if m:
                    problems.append(f"{path.relative_to(ROOT)}:{n}: physical-direction class '{m.group(0)}'")
    if not (DIST / "index.html").exists():
        problems.append("web/dist/index.html missing")
    if DIST.is_dir():
        for path in DIST.rglob("*"):
            if not path.is_file():
                continue
            data = path.read_bytes().decode("utf-8", errors="replace")
            for token in SECRETS:
                if token in data:
                    problems.append(f"{path.relative_to(ROOT)}: contains '{token}'")
    if SRC.is_dir() and DIST.is_dir() and newest_mtime(DIST) < newest_mtime(SRC):
        problems.append("web/dist is older than web/src: rebuild with npm run build")
    if problems:
        print("web check FAILED:")
        for p in problems:
            print("  " + p)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
