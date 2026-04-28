"""Layer 3 — track sessions heimdallr launched itself.

Read spawned_pids from SQLite, validate each PID is still alive (via psutil),
prune stale rows, and return a list of live entries. The detector merges these
with confidence="high" source=["self"].
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import psutil

from ..config import DB_PATH
from ..db import open_db


@dataclass
class SpawnedRow:
    pid: int
    session_id: str
    agent: str
    started_at: datetime


def _row_is_live(pid: int, started_at: float, create_time: float | None) -> bool:
    """True if pid still exists AND its create_time is consistent with our row.

    The create_time check defends against PID reuse: another process with the
    same PID that started after our wrapper's INSERT shouldn't be claimed.
    Allow a 5-second slack since our started_at uses strftime('%s','now') in
    the wrapper (whole seconds) and Process.create_time() is sub-second.
    """
    if create_time is not None:
        return create_time <= started_at + 5
    try:
        proc = psutil.Process(pid)
        return proc.create_time() <= started_at + 5
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return False


def live(
    db_path: Path | None = None,
    known_create_times: dict[int, float] | None = None,
) -> list[SpawnedRow]:
    """Return live spawned-pid rows; prune stale ones on read.

    Pass `known_create_times` (e.g. from `psutil_scan.scan()`) to skip the
    per-row `psutil.Process(pid)` syscall — a meaningful win on the detector
    hot path where the scan has already enumerated every relevant process.
    """
    db = open_db(db_path or DB_PATH)
    rows = list(db["spawned_pids"].rows)

    live_rows: list[SpawnedRow] = []
    stale_pids: list[int] = []
    for r in rows:
        pid = int(r["pid"])
        started_at = int(r["started_at"])
        ct = known_create_times.get(pid) if known_create_times is not None else None
        if _row_is_live(pid, started_at, ct):
            live_rows.append(
                SpawnedRow(
                    pid=pid,
                    session_id=r["session_id"],
                    agent=r["agent"],
                    started_at=datetime.fromtimestamp(started_at),
                )
            )
        else:
            stale_pids.append(pid)

    if stale_pids:
        # PIDs are integers (we cast on read), so direct interpolation is safe.
        placeholders = ",".join(str(p) for p in stale_pids)
        db.executescript(f"DELETE FROM spawned_pids WHERE pid IN ({placeholders});")

    return live_rows
