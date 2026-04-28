"""Configuration and constants for heimdallr."""

import os
from pathlib import Path

AGENTS = {
    "claude": {"color": "#E87B35", "badge": "claude"},
    "codex": {"color": "#00A67E", "badge": "codex"},
}

CLAUDE_DIR = Path.home() / ".claude" / "projects"
CLAUDE_IDE_DIR = Path.home() / ".claude" / "ide"
CODEX_DIR = Path.home() / ".codex" / "sessions"


def _xdg_dir(env: str, fallback: str) -> Path:
    raw = os.environ.get(env)
    base = Path(raw).expanduser() if raw else Path.home() / fallback
    return base / "heimdallr"


CACHE_DIR = _xdg_dir("XDG_CACHE_HOME", ".cache")
DATA_DIR = _xdg_dir("XDG_DATA_HOME", ".local/share")
STATE_DIR = _xdg_dir("XDG_STATE_HOME", ".local/state")

INDEX_DIR = CACHE_DIR / "tantivy"
DB_PATH = DATA_DIR / "state.db"
LOG_FILE = STATE_DIR / "heimdallr.log"

# Bump when the Tantivy schema changes; old indexes auto-rebuild.
SCHEMA_VERSION = 1

# Default RunningDetector tick interval in seconds.
DETECTOR_INTERVAL_S = 2.0

# Sessions whose JSONL was modified within this window count as "warm" (low confidence).
MTIME_WARM_THRESHOLD_S = 300.0
