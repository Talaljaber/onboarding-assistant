"""Verify the bundled e5 encoder files against the sha256 values in encoder_meta.json."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENCODER = ROOT / "models" / "e5"


def main() -> int:
    meta_path = ENCODER / "encoder_meta.json"
    if not meta_path.exists():
        print("encoder check FAILED: models/e5/encoder_meta.json missing")
        print("Fix: copy models/e5 from the release zip or the repository.")
        return 1
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    for name, sha in meta["sha256"].items():
        path = ENCODER / name
        if not path.exists():
            print(f"encoder check FAILED: {name} missing")
            return 1
        got = hashlib.sha256(path.read_bytes()).hexdigest()
        if got != sha:
            print(f"encoder check FAILED: {name} sha256 mismatch")
            return 1
    print(f"encoder OK: {meta['model_id']} dim={meta['dim']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
