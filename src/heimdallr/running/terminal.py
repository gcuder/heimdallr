"""Find the terminal window an agent runs in, or spawn a new one.

`find_terminal_pid` walks parent processes from an agent PID up to the first
ancestor that looks like a terminal emulator. The TUI uses it to decide
whether to "jump to existing terminal" vs "spawn a new window."

`spawn_new_terminal` opens a new terminal window on macOS via osascript,
auto-detecting the user's terminal app from `$TERM_PROGRAM`. On Linux we
return False so the caller falls back to `os.execvp` in place.
"""

from __future__ import annotations

import logging
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass

import psutil

logger = logging.getLogger(__name__)

# Process names we treat as terminal emulators. Match is on Path(name).name,
# lowercased for cross-platform tolerance. Includes editor hosts (VS Code,
# Cursor, Windsurf) because their integrated terminals make the editor
# itself the right "jump target."
TERMINAL_NAMES: set[str] = {
    # Standalone terminal emulators
    "terminal",
    "iterm2",
    "iterm",
    "wezterm",
    "wezterm-gui",
    "alacritty",
    "kitty",
    "hyper",
    "ghostty",
    "tabby",
    "warp",
    "stable",  # Warp's process name on some builds
    "wave",
    # Editor hosts with integrated terminals
    "code",
    "code - insiders",
    "cursor",
    "windsurf",
    "zed",
}

# Process names we explicitly walk through (shells, multiplexers,
# helper processes). Anything not in TERMINAL_NAMES and not in this set is
# also walked through, but listing the common ones keeps debug logs quieter.
_PASSTHROUGH: set[str] = {
    "tmux",
    "tmux: server",
    "screen",
    "zsh",
    "bash",
    "fish",
    "sh",
    "dash",
    "ksh",
    "login",
    "sudo",
    "node",
    "ptyhost",
    "code helper",
    "code helper (renderer)",
    "code helper (plugin)",
    "cursor helper",
    "cursor helper (renderer)",
    "cursor helper (plugin)",
}


@dataclass
class TerminalRef:
    pid: int
    name: str


def find_terminal_pid(agent_pid: int) -> TerminalRef | None:
    """Walk parents of `agent_pid`; return the first ancestor matching a known
    terminal emulator name. Returns None if none found or psutil fails.
    """
    try:
        proc = psutil.Process(agent_pid)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None
    try:
        ancestors = proc.parents()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None
    for ancestor in ancestors:
        try:
            name = (ancestor.name() or "").lower()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        bare = name.split("/")[-1]
        if bare in TERMINAL_NAMES:
            return TerminalRef(pid=ancestor.pid, name=ancestor.name())
        # Walk through shells / tmux without giving up.
        if bare in _PASSTHROUGH:
            continue
        # Unknown intermediate — keep walking, but log so we can extend the
        # set if we miss common terminals.
        logger.debug("find_terminal_pid: walking through unknown ancestor %s", bare)
    return None


def detect_terminal_app(preferred: str = "") -> str:
    """Return the terminal app to spawn windows in.

    Order of preference: explicit `preferred` arg → settings.resume.terminal →
    $TERM_PROGRAM → "Terminal".
    """
    if preferred:
        return preferred
    env = os.environ.get("TERM_PROGRAM", "")
    return _term_program_to_app(env)


def _term_program_to_app(term_program: str) -> str:
    """Map $TERM_PROGRAM values to the AppleScript app name."""
    mapping = {
        "Apple_Terminal": "Terminal",
        "iTerm.app": "iTerm",
        "WezTerm": "WezTerm",
        "ghostty": "Ghostty",
        "Hyper": "Hyper",
        "alacritty": "Alacritty",
        "kitty": "kitty",
        "Tabby": "Tabby",
    }
    return mapping.get(term_program, "Terminal")


def spawn_new_terminal(directory: str, command: list[str], app: str = "") -> bool:
    """Open a new terminal window running `cd <dir> && <command>` in the user's
    terminal app. Returns True on success, False otherwise.

    macOS-only. On other platforms, returns False so callers fall back to
    `os.execvp` in place.
    """
    if sys.platform != "darwin":
        return False

    target = detect_terminal_app(app)
    cmd_str = shlex.join(command)
    if directory:
        line = f"cd {shlex.quote(directory)} && {cmd_str}"
    else:
        line = cmd_str

    try:
        if target == "iTerm" or target == "iTerm2":
            return _spawn_iterm(line)
        return _spawn_terminal_app(line, target)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.warning("spawn_new_terminal(%s) failed: %s", target, e)
        # Last-resort fall back to Terminal.app — it's installed on every Mac.
        if target != "Terminal":
            try:
                return _spawn_terminal_app(line, "Terminal")
            except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                pass
        return False


def _spawn_terminal_app(line: str, app: str) -> bool:
    """Tell <app> to do script <line> — works for Terminal.app and most
    AppleScript-friendly emulators."""
    script = f'tell application "{app}" to do script "{_escape_applescript(line)}"\n'
    script += f'tell application "{app}" to activate'
    subprocess.run(
        ["osascript", "-e", script],
        check=True,
        capture_output=True,
        timeout=5,
    )
    return True


def _spawn_iterm(line: str) -> bool:
    """iTerm needs a different AppleScript — create window, then write text."""
    escaped = _escape_applescript(line)
    script = (
        'tell application "iTerm"\n'
        "  activate\n"
        "  create window with default profile\n"
        f'  tell current session of current window to write text "{escaped}"\n'
        "end tell"
    )
    subprocess.run(
        ["osascript", "-e", script],
        check=True,
        capture_output=True,
        timeout=5,
    )
    return True


def _escape_applescript(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')
