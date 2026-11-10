"""Verify the six official CSVs in data/official against SHA256SUMS.txt (raw bytes).

Never modifies the files. Exit 0 and print "6 files OK" on success.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OFFICIAL = ROOT / "data" / "official"
EXPECTED = {
    "knowledge_base.csv": "5122ef4691230fd629bc35372ba72cd53a4fb199fd30ef65eeed159e130a2df9",
    "sample_faq.csv": "c4cfde0f56d5daf9d8271dc85041fa4f01e5e1625c36cca55ff5ba8ea1b71cca",
    "role_scenarios.csv": "5d1f709ccd1e8b68d71444cd1bb97d9bf0e7793d5018a6e8a63de0b33c2be454",
    "suggested_learning_plan.csv": "ea73166be0a08487c82c2fcb3ee1c2cba5a63bfdf138314bf336e9e27cbfbd40",
    "sample_quiz.csv": "2a775c807d9dde2f0acc644236bbcfb57435cc36d130c7cef13499f41b9bfd2d",
    "JURY_TEST_CASES.csv": "420866950ebf8b201b7af1403c705afd30dcb82196fe53e8677525d2fc284fc0",
}


def main() -> int:
    bad: list[str] = []
    for name, sha in EXPECTED.items():
        path = OFFICIAL / name
        if not path.exists():
            bad.append(f"{name}: missing")
            continue
        got = hashlib.sha256(path.read_bytes()).hexdigest()
        if got != sha:
            bad.append(f"{name}: sha256 {got} != {sha}")
    if bad:
        print("official data check FAILED:\n  " + "\n  ".join(bad))
        print("Fix: restore data/official from the release zip or a fresh clone.")
        return 1
    print(f"{len(EXPECTED)} files OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
