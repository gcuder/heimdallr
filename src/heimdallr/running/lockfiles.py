"""Layer 4 — parse ~/.claude/ide/<port>.lock to detect IDE-attached sessions.

Verified format (PyCharm / WebStorm / VSCode write the same shape):
    {"workspaceFolders": ["/path/..."], "pid": 1842, "ideName": "PyCharm", ...}

The `pid` is the IDE's pid, not Claude's — but `workspaceFolders` tells us
"Claude Code is currently active in this directory" which lets us upgrade any
cwd-matched session to high confidence and surface the IDE name.

No Codex equivalent exists; ~/.codex/ has no lock files.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import orjson
import psutil

from ..config import CLAUDE_IDE_DIR


@dataclass
class IdeLock:
    port: int
    pid: int
    ide: str
    workspaces: list[str]


def claude_ide_workspaces(ide_dir: Path = CLAUDE_IDE_DIR) -> list[IdeLock]:
    """Read all live ~/.claude/ide/*.lock files; skip stale ones."""
    if not ide_dir.exists():
        return []

    locks: list[IdeLock] = []
    for f in ide_dir.glob("*.lock"):
        try:
            data = orjson.loads(f.read_bytes())
        except (OSError, orjson.JSONDecodeError):
            continue
        try:
            port = int(f.stem)
            pid = int(data["pid"])
        except (KeyError, ValueError):
            continue
        if not psutil.pid_exists(pid):
            continue  # stale lock — skip rather than report a dead IDE
        locks.append(
            IdeLock(
                port=port,
                pid=pid,
                ide=str(data.get("ideName", "?")),
                workspaces=list(data.get("workspaceFolders", [])),
            )
        )
    return locks
