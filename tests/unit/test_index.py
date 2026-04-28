"""Tantivy index round-trip + incremental update test."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from heimdallr.index import TantivyIndex
from heimdallr.models import Session


def _make_session(sid: str, agent: str, title: str, mtime: float) -> Session:
    return Session(
        id=sid,
        agent=agent,
        title=title,
        directory="/tmp",
        timestamp=datetime.fromtimestamp(mtime),
        content=f"» first user message about {title}\n  some assistant reply",
        message_count=2,
        mtime=mtime,
    )


def test_index_round_trip(tmp_path: Path) -> None:
    idx = TantivyIndex(index_path=tmp_path / "tantivy")

    s = _make_session("abc-123", "claude", "Refactor the auth module", 1700000000.0)
    idx.add_sessions([s])

    known = idx.get_known_sessions()
    assert known["abc-123"] == (1700000000.0, "claude")

    all_sessions = idx.get_all_sessions()
    assert len(all_sessions) == 1
    assert all_sessions[0].title == "Refactor the auth module"


def test_index_search_text(tmp_path: Path) -> None:
    idx = TantivyIndex(index_path=tmp_path / "tantivy")
    idx.add_sessions(
        [
            _make_session("a", "claude", "Investigate flaky test", 1700000001.0),
            _make_session("b", "codex", "Implement OAuth callback", 1700000002.0),
        ]
    )

    hits = idx.search("oauth")
    assert any(sid == "b" for sid, _ in hits)


def test_index_delete(tmp_path: Path) -> None:
    idx = TantivyIndex(index_path=tmp_path / "tantivy")
    idx.add_sessions(
        [
            _make_session("keep", "claude", "Keep me", 1700000001.0),
            _make_session("drop", "codex", "Drop me", 1700000002.0),
        ]
    )

    idx.delete_sessions(["drop"])
    remaining = {s.id for s in idx.get_all_sessions()}
    assert remaining == {"keep"}
