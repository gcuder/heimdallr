"""Bring an attached IDE window to the front.

macOS: AppleScript via System Events targets the IDE by PID, so even with
multiple instances of the same IDE running we activate the right one.

Linux: wmctrl falls back to matching by IDE name — best-effort.

Windows: not supported in this version.
"""

from __future__ import annotations

import shutil
import subprocess
import sys


def activate(pid: int, ide_name: str | None = None) -> tuple[bool, str]:
    """Bring the IDE process with `pid` to the foreground.

    Returns (success, human_message). The message goes to a Textual notify().
    """
    if sys.platform == "darwin":
        return _activate_macos(pid, ide_name)
    if sys.platform.startswith("linux"):
        return _activate_linux(pid, ide_name)
    return False, "Activating IDE windows is not supported on this platform."


def _activate_macos(pid: int, ide_name: str | None) -> tuple[bool, str]:
    script = (
        "tell application \"System Events\" to "
        f"set frontmost of (first process whose unix id is {pid}) to true"
    )
    try:
        subprocess.run(
            ["osascript", "-e", script],
            check=True,
            capture_output=True,
            timeout=3,
        )
    except subprocess.CalledProcessError as e:
        # If the PID-targeted activation fails (e.g. no Accessibility permission),
        # fall back to activating the app by name.
        if ide_name:
            try:
                subprocess.run(
                    ["osascript", "-e", f'tell application "{ide_name}" to activate'],
                    check=True,
                    capture_output=True,
                    timeout=3,
                )
                return True, f"Activated {ide_name} (by name; couldn't target pid {pid})"
            except subprocess.CalledProcessError:
                pass
        msg = e.stderr.decode(errors="replace").strip() or "osascript failed"
        return False, f"Could not activate IDE: {msg}"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False, "osascript not available."
    return True, f"Activated {ide_name or 'IDE'}"


def _activate_linux(pid: int, ide_name: str | None) -> tuple[bool, str]:
    if not shutil.which("wmctrl"):
        return False, "Install wmctrl to activate IDE windows on Linux."
    # wmctrl can match by PID on most distros; if not, fall back to name match.
    try:
        subprocess.run(
            ["wmctrl", "-x", "-a", str(pid)], check=True, capture_output=True, timeout=3
        )
        return True, f"Activated {ide_name or 'IDE'} (pid {pid})"
    except subprocess.CalledProcessError:
        if ide_name:
            try:
                subprocess.run(
                    ["wmctrl", "-a", ide_name], check=True, capture_output=True, timeout=3
                )
                return True, f"Activated {ide_name} (by name)"
            except subprocess.CalledProcessError:
                pass
        return False, f"wmctrl couldn't find a window for pid {pid}"
