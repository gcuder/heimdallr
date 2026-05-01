"""User settings — TOML-backed at ~/.config/heimdallr/config.toml.

Read once on startup, written when the user toggles in the TUI. Keep the
schema small and forgiving: missing keys fall back to defaults, malformed
files don't crash the app.
"""

from __future__ import annotations

import logging
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


def _config_dir() -> Path:
    raw = os.environ.get("XDG_CONFIG_HOME")
    base = Path(raw).expanduser() if raw else Path.home() / ".config"
    return base / "heimdallr"


CONFIG_PATH = _config_dir() / "config.toml"

# Sessions whose `directory` starts with one of these prefixes are hidden by
# default when filters.hide_claude_mem is True. Stored as the user-resolved
# absolute path; matched as a prefix on Session.directory.
CLAUDE_MEM_PREFIX = str((Path.home() / ".claude-mem").resolve())


@dataclass
class FilterSettings:
    hide_claude_mem: bool = True
    hide_directories: list[str] = field(default_factory=list)


@dataclass
class ResumeSettings:
    terminal: str = ""  # empty = auto-detect from $TERM_PROGRAM


@dataclass
class Settings:
    filters: FilterSettings = field(default_factory=FilterSettings)
    resume: ResumeSettings = field(default_factory=ResumeSettings)

    def hidden_prefixes(self) -> list[str]:
        """All directory prefixes that should be filtered out, with ~ expanded."""
        out: list[str] = []
        if self.filters.hide_claude_mem:
            out.append(CLAUDE_MEM_PREFIX)
        for d in self.filters.hide_directories:
            out.append(str(Path(d).expanduser()))
        return out


def load() -> Settings:
    """Read settings from disk; return defaults on any error."""
    if not CONFIG_PATH.exists():
        return Settings()
    try:
        with open(CONFIG_PATH, "rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        logger.warning("Could not read %s: %s; using defaults", CONFIG_PATH, e)
        return Settings()

    filters_raw = data.get("filters", {}) or {}
    resume_raw = data.get("resume", {}) or {}
    return Settings(
        filters=FilterSettings(
            hide_claude_mem=bool(filters_raw.get("hide_claude_mem", True)),
            hide_directories=list(filters_raw.get("hide_directories", []) or []),
        ),
        resume=ResumeSettings(
            terminal=str(resume_raw.get("terminal", "") or ""),
        ),
    )


def save(s: Settings) -> None:
    """Write settings atomically. Creates the config dir if missing."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    body = _to_toml(s)
    tmp = CONFIG_PATH.with_suffix(".toml.tmp")
    tmp.write_text(body, encoding="utf-8")
    tmp.replace(CONFIG_PATH)


def _to_toml(s: Settings) -> str:
    """Hand-written TOML writer for our tiny shape — avoids an extra dep."""
    lines: list[str] = [
        "[filters]",
        f"hide_claude_mem = {'true' if s.filters.hide_claude_mem else 'false'}",
        f"hide_directories = {_toml_string_list(s.filters.hide_directories)}",
        "",
        "[resume]",
        f'terminal = "{_escape(s.resume.terminal)}"',
        "",
    ]
    return "\n".join(lines)


def _toml_string_list(items: list[str]) -> str:
    if not items:
        return "[]"
    quoted = ", ".join(f'"{_escape(x)}"' for x in items)
    return f"[{quoted}]"


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


# Module-level cached settings — loaded lazily on first access. The TUI
# reloads explicitly when persisting a change.
_cached: Settings | None = None


def current() -> Settings:
    global _cached
    if _cached is None:
        _cached = load()
    return _cached


def update(s: Settings) -> None:
    """Persist new settings and update the cached copy."""
    global _cached
    save(s)
    _cached = s
