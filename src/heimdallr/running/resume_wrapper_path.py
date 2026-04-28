"""Locate the resume_wrapper.sh shipped with heimdallr."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path


def wrapper_path() -> Path:
    """Return an absolute path to resume_wrapper.sh.

    `files()` returns a Traversable; on a normal disk install this is already
    a Path. For zip installs it would need a temporary extraction step, but
    heimdallr is currently distributed as a regular wheel so disk paths work.
    """
    p = files("heimdallr.running") / "resume_wrapper.sh"
    return Path(str(p))
