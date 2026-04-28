"""User-flag persistence for sessions: pin / favorite / tags / open-count.

Backed by the `bookmarks` table created in db.py. Tantivy stays the source
of truth for searchable session content; this module owns the per-user state
that flips frequently and shouldn't churn the index.
"""

from __future__ import annotations

import time
from pathlib import Path

from .config import DB_PATH
from .db import open_db


def get_pinned_ids(db_path: Path | None = None) -> set[str]:
    db = open_db(db_path or DB_PATH)
    return {
        row["session_id"]
        for row in db["bookmarks"].rows_where("pinned = 1")
    }


def is_pinned(session_id: str, db_path: Path | None = None) -> bool:
    db = open_db(db_path or DB_PATH)
    rows = list(db["bookmarks"].rows_where("session_id = ?", [session_id]))
    return bool(rows and rows[0].get("pinned"))


def toggle_pin(session_id: str, db_path: Path | None = None) -> bool:
    """Flip the pinned state. Returns the new value."""
    db = open_db(db_path or DB_PATH)
    new = not is_pinned(session_id, db_path)
    db["bookmarks"].upsert(
        {"session_id": session_id, "pinned": new},
        pk="session_id",
        alter=False,
    )
    return new


def record_open(session_id: str, db_path: Path | None = None) -> None:
    """Increment open_count + stamp last_opened_at. Called when user resumes."""
    db = open_db(db_path or DB_PATH)
    rows = list(db["bookmarks"].rows_where("session_id = ?", [session_id]))
    prior_count = rows[0].get("open_count") if rows else 0
    db["bookmarks"].upsert(
        {
            "session_id": session_id,
            "last_opened_at": int(time.time()),
            "open_count": (prior_count or 0) + 1,
        },
        pk="session_id",
        alter=False,
    )
