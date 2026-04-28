"""Layer 1 — scan psutil for running claude/codex processes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import psutil

# We pre-filter by name then re-fetch full info only for matches — much cheaper
# than asking psutil for cmdline+cwd on every process on the system.
_INTERESTING = {"claude", "codex"}


@dataclass
class ProcInfo:
    pid: int
    exe: str
    cmdline: list[str]
    cwd: str | None
    create_time: float


def scan() -> list[ProcInfo]:
    """Return one ProcInfo per running claude/codex process."""
    out: list[ProcInfo] = []
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            name = proc.info.get("name") or ""
            if Path(name).name not in _INTERESTING:
                continue
            full = proc.as_dict(attrs=["pid", "name", "cmdline", "cwd", "create_time"])
            cmdline = full.get("cmdline") or []
            if not cmdline:
                continue
            exe = Path(cmdline[0]).name
            if exe not in _INTERESTING:
                continue
            out.append(
                ProcInfo(
                    pid=full["pid"],
                    exe=exe,
                    cmdline=cmdline,
                    cwd=full.get("cwd"),
                    create_time=full["create_time"],
                )
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return out
