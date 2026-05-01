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

# Built-in Textual themes the settings UI exposes.
THEMES: list[str] = [
    "textual-dark",
    "textual-light",
    "nord",
    "dracula",
    "gruvbox",
    "monokai",
    "tokyo-night",
    "solarized-light",
]

TERMINAL_CHOICES: list[str] = [
    "",  # auto-detect
    "Terminal",
    "iTerm",
    "WezTerm",
    "Alacritty",
    "kitty",
    "Ghostty",
]

TRANSFER_IDE_CHOICES: list[str] = [
    "",  # auto
    "Cursor",
    "VS Code",
    "Windsurf",
    "Zed",
    "Ghostty",
]

VIEW_MODES: list[str] = ["all", "running", "recent"]
SORT_MODES: list[str] = ["recent", "running", "pinned", "project"]
AGENT_FILTERS: list[str | None] = [None, "claude", "codex"]


@dataclass
class DisplaySettings:
    theme: str = "textual-dark"
    show_logo: bool = True
    sort_mode: str = "recent"
    show_preview: bool = True


@dataclass
class FilterSettings:
    hide_claude_mem: bool = True
    hide_directories: list[str] = field(default_factory=list)
    default_agent: str | None = None
    default_view: str = "all"


@dataclass
class ResumeSettings:
    terminal: str = ""
    yolo_default: bool = False
    prefer_ide: bool = False


@dataclass
class TransferSettings:
    target_ide: str = ""


@dataclass
class NotificationSettings:
    default_timeout_s: float = 3.0
    error_timeout_s: float = 5.0
    auto_dismiss_errors: bool = True


@dataclass
class KeybindingSettings:
    overrides: dict[str, str] = field(default_factory=dict)


@dataclass
class Settings:
    display: DisplaySettings = field(default_factory=DisplaySettings)
    filters: FilterSettings = field(default_factory=FilterSettings)
    resume: ResumeSettings = field(default_factory=ResumeSettings)
    transfer: TransferSettings = field(default_factory=TransferSettings)
    notifications: NotificationSettings = field(default_factory=NotificationSettings)
    keybindings: KeybindingSettings = field(default_factory=KeybindingSettings)

    def hidden_prefixes(self) -> list[str]:
        """All directory prefixes that should be filtered out, with ~ expanded."""
        out: list[str] = []
        if self.filters.hide_claude_mem:
            out.append(CLAUDE_MEM_PREFIX)
        for d in self.filters.hide_directories:
            if d.strip():
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

    display_raw = data.get("display", {}) or {}
    filters_raw = data.get("filters", {}) or {}
    resume_raw = data.get("resume", {}) or {}
    transfer_raw = data.get("transfer", {}) or {}
    notif_raw = data.get("notifications", {}) or {}
    keybind_raw = data.get("keybindings", {}) or {}

    return Settings(
        display=DisplaySettings(
            theme=str(display_raw.get("theme", "textual-dark") or "textual-dark"),
            show_logo=bool(display_raw.get("show_logo", True)),
            sort_mode=str(display_raw.get("sort_mode", "recent") or "recent"),
            show_preview=bool(display_raw.get("show_preview", True)),
        ),
        filters=FilterSettings(
            hide_claude_mem=bool(filters_raw.get("hide_claude_mem", True)),
            hide_directories=list(filters_raw.get("hide_directories", []) or []),
            default_agent=_optional_str(filters_raw.get("default_agent")),
            default_view=str(filters_raw.get("default_view", "all") or "all"),
        ),
        resume=ResumeSettings(
            terminal=str(resume_raw.get("terminal", "") or ""),
            yolo_default=bool(resume_raw.get("yolo_default", False)),
            prefer_ide=bool(resume_raw.get("prefer_ide", False)),
        ),
        transfer=TransferSettings(
            target_ide=str(transfer_raw.get("target_ide", "") or ""),
        ),
        notifications=NotificationSettings(
            default_timeout_s=_to_float(notif_raw.get("default_timeout_s"), 3.0),
            error_timeout_s=_to_float(notif_raw.get("error_timeout_s"), 5.0),
            auto_dismiss_errors=bool(notif_raw.get("auto_dismiss_errors", True)),
        ),
        keybindings=KeybindingSettings(
            overrides=dict(keybind_raw.get("overrides", {}) or {}),
        ),
    )


def _optional_str(value: object) -> str | None:
    if value in (None, "", "all"):
        return None
    return str(value)


def _to_float(value: object, fallback: float) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return fallback


def save(s: Settings) -> None:
    """Write settings atomically. Creates the config dir if missing."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    body = _to_toml(s)
    tmp = CONFIG_PATH.with_suffix(".toml.tmp")
    tmp.write_text(body, encoding="utf-8")
    tmp.replace(CONFIG_PATH)


def _to_toml(s: Settings) -> str:
    """Hand-written TOML writer for our tiny shape — avoids an extra dep."""
    lines: list[str] = []

    lines += [
        "[display]",
        f'theme = "{_escape(s.display.theme)}"',
        f"show_logo = {_b(s.display.show_logo)}",
        f'sort_mode = "{_escape(s.display.sort_mode)}"',
        f"show_preview = {_b(s.display.show_preview)}",
        "",
    ]

    default_agent = s.filters.default_agent or ""
    lines += [
        "[filters]",
        f"hide_claude_mem = {_b(s.filters.hide_claude_mem)}",
        f"hide_directories = {_toml_string_list(s.filters.hide_directories)}",
        f'default_agent = "{_escape(default_agent)}"',
        f'default_view = "{_escape(s.filters.default_view)}"',
        "",
    ]

    lines += [
        "[resume]",
        f'terminal = "{_escape(s.resume.terminal)}"',
        f"yolo_default = {_b(s.resume.yolo_default)}",
        f"prefer_ide = {_b(s.resume.prefer_ide)}",
        "",
    ]

    lines += [
        "[transfer]",
        f'target_ide = "{_escape(s.transfer.target_ide)}"',
        "",
    ]

    lines += [
        "[notifications]",
        f"default_timeout_s = {s.notifications.default_timeout_s}",
        f"error_timeout_s = {s.notifications.error_timeout_s}",
        f"auto_dismiss_errors = {_b(s.notifications.auto_dismiss_errors)}",
        "",
    ]

    lines.append("[keybindings.overrides]")
    for action, key in sorted(s.keybindings.overrides.items()):
        lines.append(f'{action} = "{_escape(key)}"')
    lines.append("")

    return "\n".join(lines)


def _b(value: bool) -> str:
    return "true" if value else "false"


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


def reset_section(section: str) -> Settings:
    """Replace one section with its defaults; persist; return new Settings."""
    s = current()
    defaults = Settings()
    if section == "display":
        s.display = defaults.display
    elif section == "filters":
        s.filters = defaults.filters
    elif section == "resume":
        s.resume = defaults.resume
    elif section == "transfer":
        s.transfer = defaults.transfer
    elif section == "notifications":
        s.notifications = defaults.notifications
    elif section == "keybindings":
        s.keybindings = defaults.keybindings
    update(s)
    return s
