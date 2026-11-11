"""Remove the old anonymous demo profiles («متدرب N»): profiles that are not linked to an intern.

    python scripts/purge_demo_profiles.py            # dry run: prints what would be removed
    python scripts/purge_demo_profiles.py --apply    # deletes them

Works on the configured store (Supabase when configured and reachable, else the local SQLite file; set
STORE=local to force the local file). Deletes those profiles with their progress, quiz and scenario
attempts; turn logs are kept with their profile link cleared. Profiles linked to an intern are never
touched. Prints counts only (no ids, no names). Run it after supabase/migrations/0002_interns.sql.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.store import get_store, reset_store  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="delete (default: dry run)")
    args = ap.parse_args(argv)
    store = get_store(get_settings())
    try:
        counts = store.purge_demo_profiles(apply=args.apply)
        if not counts:
            print(f"purge failed on the {store.name} store (see the log); nothing changed")
            return 1
        verb = "deleted" if args.apply else "would delete (dry run, pass --apply)"
        print(f"store: {store.name}")
        print(f"{verb}: {counts['profiles']} demo profiles, {counts['progress']} progress rows, "
              f"{counts['quiz_attempts']} quiz attempts, {counts['scenario_attempts']} scenario attempts")
        print(f"turn logs kept, profile link {'cleared' if args.apply else 'to clear'}: {counts['turn_logs']}")
        return 0
    finally:
        reset_store()


if __name__ == "__main__":
    sys.exit(main())
