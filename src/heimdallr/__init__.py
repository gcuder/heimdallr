"""heimdallr: a TUI for managing Claude Code and Codex sessions."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("heimdallr")
except PackageNotFoundError:
    __version__ = "0.0.0+local"
