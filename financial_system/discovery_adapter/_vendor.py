"""
The only place financial_system decides WHERE Discovery.AI's code lives.
Every other discovery_adapter module calls ensure_on_path() before any
`from backend...` import (that import name is Discovery.AI's own top-level
package, only resolvable once vendor/discovery-ai is on sys.path).

No other module under financial_system/ may import `backend.*` — that's the
whole point of this package being the sole boundary (Rules.md).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VENDOR_PATH = REPO_ROOT / "vendor" / "discovery-ai"


def ensure_on_path() -> None:
    if not VENDOR_PATH.exists():
        raise ImportError(
            f"Discovery.AI not found at {VENDOR_PATH}. Clone it first: "
            f"git clone https://github.com/TheNova6000/Discovery.AI.git {VENDOR_PATH}"
        )
    p = str(VENDOR_PATH)
    if p not in sys.path:
        sys.path.insert(0, p)
