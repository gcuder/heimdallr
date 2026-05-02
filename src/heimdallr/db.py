"""SQLite state — bookmarks, spawned PIDs, transfer history.

Tantivy is the search source of truth; this DB is the state source of truth.
The two never overlap on responsibility.
"""

from __future__ import annotations

from pathlib import Path

import sqlite_utils

from .config import DB_PATH

# Cache "we already migrated this path" so the hot detector loop and
# every bookmark op don't re-run table_names() + 4 create-if-not-exists.
# Connections themselves stay per-call (cheap, and avoids cross-thread
# sharing of sqlite3 handles).
_MIGRATED_PATHS: set[str] = set()


def open_db(path: Path | None = None) -> sqlite_utils.Database:
    """Open (creating if necessary) and return the heimdallr SQLite DB.

    Idempotent — safe to call from multiple sites; schema migrates exactly
    once per process per path.
    """
    db_path = path if path is not None else DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite_utils.Database(str(db_path))
    key = str(db_path)
    if key not in _MIGRATED_PATHS:
        _migrate(db)
        _MIGRATED_PATHS.add(key)
    return db


def _migrate(db: sqlite_utils.Database) -> None:
    db["schema_version"].create({"version": int}, pk="version", if_not_exists=True)

    rows = list(db["schema_version"].rows)
    if not rows:
        db["schema_version"].upsert({"version": 0}, pk="version")  # type: ignore[arg-type]
        rows = list(db["schema_version"].rows)
    version = rows[0]["version"] if rows else 0

    if version < 1:
        # Phase 1 tables. Sessions denormalized from Tantivy for SQL joins
        # against bookmarks; the canonical source of truth is still Tantivy.
        db["sessions"].create(
            {
                "id": str,
                "agent": str,
                "title": str,
                "directory": str,
                "first_message": str,
                "token_count": int,
                "raw_path": str,
                "created_at": int,
                "updated_at": int,
            },
            pk="id",
            if_not_exists=True,
        )
        db["bookmarks"].create(
            {
                "session_id": str,
                "pinned": bool,
                "favorite": bool,
                "tags": str,  # JSON array
                "last_opened_at": int,
                "open_count": int,
            },
            pk="session_id",
            if_not_exists=True,
        )
        # Phase 3 tables — created early so we can read them without a re-migrate.
        db["spawned_pids"].create(
            {
                "pid": int,
                "session_id": str,
                "agent": str,
                "started_at": int,
            },
            pk="pid",
            if_not_exists=True,
        )
        db["spawned_pids"].create_index(["session_id"], if_not_exists=True)
        db["transfers"].create(
            {
                "id": int,
                "source_session_id": str,
                "target_session_id": str,
                "source_agent": str,
                "target_agent": str,
                "strategy": str,
                "method": str,
                "compacted_text": str,
                "token_count": int,
                "command_used": str,
                "executed_at": int,
            },
            pk="id",
            if_not_exists=True,
        )
        db["schema_version"].upsert({"version": 1}, pk="version")  # type: ignore[arg-type]
