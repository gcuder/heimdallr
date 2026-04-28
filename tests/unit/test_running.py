"""Tests for the running-detection layers."""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from heimdallr.adapters.claude import ClaudeAdapter
from heimdallr.adapters.codex import CodexAdapter
from heimdallr.models import Session
from heimdallr.running import detector as detector_mod
from heimdallr.running import lockfiles, mtime_signal
from heimdallr.running.detector import RunningDetector
from heimdallr.running.psutil_scan import ProcInfo

# ---- Layer 2: mtime ---------------------------------------------------------


def test_mtime_threshold_classifies_recent_as_warm() -> None:
    now = time.time()
    mtimes = {"recent": now - 60, "old": now - 600}
    warm = mtime_signal.warm_session_ids(mtimes, threshold_s=300)
    assert warm == {"recent"}


# ---- Layer 4: lockfiles -----------------------------------------------------


def test_claude_ide_workspaces_parses_real_format(tmp_path: Path) -> None:
    ide_dir = tmp_path / "ide"
    ide_dir.mkdir()
    # Verified format from a real PyCharm lock on disk.
    (ide_dir / "49916.lock").write_text(
        json.dumps(
            {
                "workspaceFolders": ["/Users/x/proj"],
                "pid": 1,  # PID 1 always exists (init/launchd)
                "ideName": "PyCharm",
                "transport": "ws",
                "runningInWindows": False,
                "authToken": "tok",
            }
        )
    )

    locks = lockfiles.claude_ide_workspaces(ide_dir=ide_dir)
    assert len(locks) == 1
    assert locks[0].port == 49916
    assert locks[0].ide == "PyCharm"
    assert locks[0].workspaces == ["/Users/x/proj"]


def test_claude_ide_workspaces_skips_stale_lock(tmp_path: Path) -> None:
    ide_dir = tmp_path / "ide"
    ide_dir.mkdir()
    # PID 999999 is virtually guaranteed not to exist.
    (ide_dir / "12345.lock").write_text(
        json.dumps({"workspaceFolders": [], "pid": 999999, "ideName": "x"})
    )
    assert lockfiles.claude_ide_workspaces(ide_dir=ide_dir) == []


def test_claude_ide_workspaces_handles_missing_dir(tmp_path: Path) -> None:
    assert lockfiles.claude_ide_workspaces(ide_dir=tmp_path / "nonexistent") == []


def test_claude_ide_workspaces_skips_malformed(tmp_path: Path) -> None:
    ide_dir = tmp_path / "ide"
    ide_dir.mkdir()
    (ide_dir / "1.lock").write_text("not json")
    assert lockfiles.claude_ide_workspaces(ide_dir=ide_dir) == []


# ---- Detector merge logic ---------------------------------------------------


def _session(sid: str, agent: str = "claude", directory: str = "/p", mtime: float | None = None) -> Session:
    return Session(
        id=sid,
        agent=agent,
        title="t",
        directory=directory,
        timestamp=datetime.fromtimestamp(mtime or time.time()),
        content="",
        message_count=1,
        mtime=mtime if mtime is not None else time.time(),
    )


def test_detector_psutil_high_confidence_when_resume_in_argv() -> None:
    sessions = [_session("abc-1")]
    detector = RunningDetector(
        adapters=[ClaudeAdapter(), CodexAdapter()],
        get_sessions=lambda: sessions,
    )

    fake_proc = ProcInfo(
        pid=1234,
        exe="claude",
        cmdline=["claude", "--resume", "abc-1"],
        cwd="/p",
        create_time=time.time(),
    )
    with patch.object(detector_mod.psutil_scan, "scan", return_value=[fake_proc]):
        with patch.object(detector_mod.lockfiles, "claude_ide_workspaces", return_value=[]):
            info = detector.snapshot()

    assert "abc-1" in info
    assert info["abc-1"].is_running is True
    assert info["abc-1"].confidence == "high"
    assert info["abc-1"].pid == 1234
    assert "psutil" in info["abc-1"].source


def test_detector_psutil_medium_confidence_for_bare_claude_via_cwd() -> None:
    sessions = [_session("abc-1", directory="/proj")]
    detector = RunningDetector(
        adapters=[ClaudeAdapter(), CodexAdapter()],
        get_sessions=lambda: sessions,
    )

    fake_proc = ProcInfo(
        pid=1234, exe="claude", cmdline=["claude"], cwd="/proj", create_time=time.time(),
    )
    with patch.object(detector_mod.psutil_scan, "scan", return_value=[fake_proc]):
        with patch.object(detector_mod.lockfiles, "claude_ide_workspaces", return_value=[]):
            info = detector.snapshot()

    assert info["abc-1"].confidence == "medium"


def test_detector_lock_file_promotes_confidence_and_attaches_ide() -> None:
    sessions = [_session("abc-1", directory="/proj")]
    detector = RunningDetector(
        adapters=[ClaudeAdapter(), CodexAdapter()],
        get_sessions=lambda: sessions,
    )

    fake_proc = ProcInfo(
        pid=1234, exe="claude", cmdline=["claude"], cwd="/proj", create_time=time.time(),
    )
    fake_lock = lockfiles.IdeLock(port=49916, pid=4242, ide="PyCharm", workspaces=["/proj"])

    with patch.object(detector_mod.psutil_scan, "scan", return_value=[fake_proc]):
        with patch.object(
            detector_mod.lockfiles, "claude_ide_workspaces", return_value=[fake_lock]
        ):
            info = detector.snapshot()

    assert info["abc-1"].confidence == "high"
    assert info["abc-1"].ide == "PyCharm"
    assert info["abc-1"].ide_pid == 4242
    assert "lock" in info["abc-1"].source


def test_detector_mtime_only_session_is_low_confidence() -> None:
    # Recently-modified session, no process scanning hits it.
    sessions = [_session("warm", mtime=time.time() - 30)]
    detector = RunningDetector(
        adapters=[ClaudeAdapter(), CodexAdapter()],
        get_sessions=lambda: sessions,
    )
    with patch.object(detector_mod.psutil_scan, "scan", return_value=[]):
        with patch.object(detector_mod.lockfiles, "claude_ide_workspaces", return_value=[]):
            info = detector.snapshot()

    assert info["warm"].confidence == "low"
    assert info["warm"].source == ["mtime"]


def test_detector_skips_old_sessions() -> None:
    sessions = [_session("old", mtime=time.time() - 10_000)]
    detector = RunningDetector(
        adapters=[ClaudeAdapter(), CodexAdapter()],
        get_sessions=lambda: sessions,
    )
    with patch.object(detector_mod.psutil_scan, "scan", return_value=[]):
        with patch.object(detector_mod.lockfiles, "claude_ide_workspaces", return_value=[]):
            info = detector.snapshot()

    assert info == {}
