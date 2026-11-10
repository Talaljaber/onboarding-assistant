"""Root test configuration: makes the repo importable and keeps every test hermetic.

Every test runs offline (OFFLINE=1), with no OpenRouter key and the local store.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["OFFLINE"] = "1"
os.environ["OPENROUTER_API_KEY"] = ""
os.environ["STORE"] = "local"
