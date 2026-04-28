"""Layer 2 — recent JSONL mtime → low-confidence "warm" running signal."""

from __future__ import annotations

import time

from ..config import MTIME_WARM_THRESHOLD_S


def warm_session_ids(
    mtimes: dict[str, float], threshold_s: float = MTIME_WARM_THRESHOLD_S
) -> set[str]:
    """Return ids whose JSONL was modified within `threshold_s` seconds."""
    now = time.time()
    return {sid for sid, mtime in mtimes.items() if (now - mtime) < threshold_s}
