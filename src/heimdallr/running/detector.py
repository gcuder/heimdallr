"""Merge all running-detection layers into a single dict[session_id, RunningInfo].

Runs on a background thread; posts `RunningSnapshot` messages to a Textual app.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterable
from datetime import datetime

from textual.message import Message

from ..adapters import ToolAdapter
from ..config import DETECTOR_INTERVAL_S, MTIME_WARM_THRESHOLD_S
from ..models import RunningInfo, Session
from . import lockfiles, mtime_signal, pid_tracker, psutil_scan


class RunningSnapshot(Message):
    """Posted to the Textual app when a fresh detector snapshot is ready."""

    def __init__(self, info: dict[str, RunningInfo]) -> None:
        self.info = info
        super().__init__()


class RunningDetector:
    """Background detector — call `start(post)` with a Textual `post_message` callable."""

    def __init__(
        self,
        adapters: Iterable[ToolAdapter],
        get_sessions: Callable[[], list[Session]],
        interval_s: float = DETECTOR_INTERVAL_S,
        mtime_threshold_s: float = MTIME_WARM_THRESHOLD_S,
    ) -> None:
        self._adapters = {a.name: a for a in adapters}
        self._get_sessions = get_sessions
        self.interval_s = interval_s
        self.mtime_threshold_s = mtime_threshold_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_info: dict[str, RunningInfo] | None = None

    # ---- public API ------------------------------------------------------

    def start(self, post: Callable[[RunningSnapshot], None]) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, args=(post,), daemon=True, name="heimdallr-detector"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def snapshot(self) -> dict[str, RunningInfo]:
        sessions = self._get_sessions()
        return self._compute(sessions)

    # ---- internals -------------------------------------------------------

    def _loop(self, post: Callable[[RunningSnapshot], None]) -> None:
        while not self._stop.is_set():
            try:
                info = self.snapshot()
                if info != self._last_info:
                    self._last_info = info
                    post(RunningSnapshot(info))
            except Exception:
                # Detector errors must never crash the TUI.
                pass
            self._stop.wait(self.interval_s)

    def _compute(self, sessions: list[Session]) -> dict[str, RunningInfo]:
        by_id: dict[str, RunningInfo] = {}
        cwd_to_session: dict[tuple[str, str], Session] = self._build_cwd_index(sessions)
        mtimes: dict[str, float] = {s.id: s.mtime for s in sessions}

        # Run the process scan once and reuse it for both Layer 1 and Layer 3
        # (pid_tracker validation), so we don't issue an extra psutil.Process
        # call per spawned-pid row.
        procs = psutil_scan.scan()
        create_times = {p.pid: p.create_time for p in procs}

        # Layer 3 — sessions we launched ourselves. Highest authority since
        # we know exactly which session each PID belongs to.
        try:
            for row in pid_tracker.live(known_create_times=create_times):
                by_id[row.session_id] = RunningInfo(
                    is_running=True,
                    confidence="high",
                    pid=row.pid,
                    started_at=row.started_at,
                    source=["self"],
                )
        except Exception:
            pass

        for proc in procs:
            adapter = self._adapters.get(proc.exe)
            if adapter is None:
                continue
            try:
                sid, confidence = adapter.process_match(_FakeProcInfo(proc))
            except Exception:
                continue
            if sid is None and proc.cwd:
                # Medium confidence cwd fallback: pick the most recent session
                # for this (agent, cwd) pair.
                match = cwd_to_session.get((proc.exe, proc.cwd))
                if match is not None:
                    sid = match.id
                    confidence = "medium"
            if sid is None:
                continue
            existing = by_id.get(sid)
            sources = (existing.source if existing else []) + ["psutil"]
            # Don't downgrade an existing high-confidence "self" entry by
            # appending psutil — but do enrich its source list and pid.
            new_confidence = (
                "high" if existing and existing.confidence == "high" else confidence
            )
            by_id[sid] = RunningInfo(
                is_running=True,
                confidence=new_confidence,
                pid=proc.pid,
                started_at=existing.started_at if existing else datetime.fromtimestamp(proc.create_time),
                source=sources,
            )

        # Layer 4 — IDE lockfiles (Claude only) upgrade matching cwd sessions
        ide_by_cwd: dict[str, tuple[str, int]] = {}
        for lock in lockfiles.claude_ide_workspaces():
            for ws in lock.workspaces:
                ide_by_cwd[ws] = (lock.ide, lock.pid)
        if ide_by_cwd:
            sessions_by_id = {s.id: s for s in sessions}
            # Promote already-detected running sessions whose cwd matches a workspace
            for sid, info in by_id.items():
                s = sessions_by_id.get(sid)
                if s and s.directory in ide_by_cwd:
                    info.confidence = "high"
                    if "lock" not in info.source:
                        info.source.append("lock")
                    info.ide, info.ide_pid = ide_by_cwd[s.directory]
            # Promote sessions that are NOT in by_id but live in an IDE workspace —
            # the IDE is open so Claude is presumably attachable. Use the most
            # recent session per workspace as a stand-in.
            for cwd, (ide, ide_pid) in ide_by_cwd.items():
                key = ("claude", cwd)
                match = cwd_to_session.get(key)
                if match is None:
                    continue
                if match.id in by_id:
                    continue
                by_id[match.id] = RunningInfo(
                    is_running=True,
                    confidence="medium",
                    pid=None,
                    started_at=None,
                    source=["lock"],
                    ide=ide,
                    ide_pid=ide_pid,
                )

        # Layer 2 — mtime warm. Only adds entries no other layer caught.
        warm = mtime_signal.warm_session_ids(mtimes, self.mtime_threshold_s)
        for sid in warm:
            if sid in by_id:
                continue
            by_id[sid] = RunningInfo(
                is_running=True,
                confidence="low",
                pid=None,
                started_at=None,
                source=["mtime"],
            )

        return by_id

    def _build_cwd_index(self, sessions: list[Session]) -> dict[tuple[str, str], Session]:
        """Map (agent, cwd) → most-recent session — used to disambiguate bare processes."""
        out: dict[tuple[str, str], Session] = {}
        for s in sessions:
            if not s.directory:
                continue
            key = (s.agent, s.directory)
            existing = out.get(key)
            if existing is None or s.mtime > existing.mtime:
                out[key] = s
        return out


class _FakeProcInfo:
    """Adapter-side `process_match` expects an object with `.info` dict.

    Wrapping our dataclass keeps the adapter contract psutil-shaped without
    forcing the detector to construct full psutil.Process instances.
    """

    def __init__(self, p: psutil_scan.ProcInfo) -> None:
        self.info = {
            "pid": p.pid,
            "name": p.exe,
            "cmdline": p.cmdline,
            "cwd": p.cwd,
            "create_time": p.create_time,
        }
