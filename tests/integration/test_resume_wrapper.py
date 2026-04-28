"""Integration test: spawn /bin/sleep via resume_wrapper.sh, verify PID tracking.

This is the load-bearing piece of Phase 3 — if the wrapper doesn't preserve
its PID across exec, self-PID tracking is broken. The test exercises the real
shell, real sqlite3 binary, and real psutil pid validation.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

import psutil
import pytest

from heimdallr.db import open_db
from heimdallr.running import pid_tracker, wrapper_path

pytestmark = pytest.mark.skipif(
    shutil.which("sqlite3") is None or shutil.which("sleep") is None,
    reason="sqlite3 and /bin/sleep required",
)


def test_wrapper_records_pid_then_pid_tracker_validates(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    open_db(db_path)  # initialize schema

    wrapper = str(wrapper_path())
    assert os.access(wrapper, os.X_OK), "resume_wrapper.sh must be executable"

    # Spawn `/bin/sleep 60` via the wrapper. POSIX preserves the shell's PID
    # across `exec sleep 60`, so the recorded PID should equal the sleep pid.
    proc = subprocess.Popen(
        [
            "/bin/sh",
            wrapper,
            str(db_path),
            "sess-test-1",
            "claude",
            "/bin/sleep",
            "60",
        ]
    )
    try:
        # Give the wrapper a moment to do its INSERT and exec.
        time.sleep(0.5)

        db = open_db(db_path)
        rows = list(db["spawned_pids"].rows)
        assert len(rows) == 1, f"expected 1 spawned_pids row, got {rows}"
        row = rows[0]
        assert row["session_id"] == "sess-test-1"
        assert row["agent"] == "claude"
        # POSIX: PID survives exec — wrapper's $$ becomes the sleep process's pid.
        assert row["pid"] == proc.pid

        # pid_tracker.live() should return our row.
        live = pid_tracker.live(db_path)
        assert len(live) == 1
        assert live[0].pid == proc.pid
        assert live[0].session_id == "sess-test-1"
    finally:
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=5)

    # After the process is gone, pid_tracker should prune the row.
    # Wait a beat to make sure the OS reaped the zombie.
    deadline = time.time() + 2.0
    while psutil.pid_exists(proc.pid) and time.time() < deadline:
        time.sleep(0.1)

    live_after = pid_tracker.live(db_path)
    assert live_after == []
    db_after = open_db(db_path)
    assert list(db_after["spawned_pids"].rows) == []
