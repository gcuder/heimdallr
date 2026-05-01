"""Tests for the hidden-directories filter applied in SessionSearch."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from heimdallr import settings
from heimdallr.models import Session
from heimdallr.search import SessionSearch


@pytest.fixture(autouse=True)
def isolate_settings(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "CONFIG_PATH", tmp_path / "config.toml")
    monkeypatch.setattr(settings, "_cached", None)
    yield


def _session(sid: str, directory: str) -> Session:
    return Session(
        id=sid,
        agent="claude",
        title=f"title {sid}",
        directory=directory,
        timestamp=datetime.now(),
        content=f"» hello {sid}\n\n  hi {sid}",
        message_count=1,
        mtime=0.0,
    )


def _build_search(sessions: list[Session]) -> SessionSearch:
    s = SessionSearch.__new__(SessionSearch)
    s.adapters = []
    s._sessions = sessions
    s._sessions_by_id = {x.id: x for x in sessions}
    s._streaming_in_progress = False

    fake_index = MagicMock()
    fake_index.search.return_value = [(x.id, 1.0) for x in sessions]
    fake_index.get_session_count.return_value = len(sessions)
    s._index = fake_index
    return s


def test_search_drops_claude_mem_when_hidden(monkeypatch) -> None:
    home = str(Path.home())
    sessions = [
        _session("a", f"{home}/.claude-mem/observer-sessions"),
        _session("b", f"{home}/projects/normal"),
        _session("c", f"{home}/.claude-mem/other/path"),
    ]
    s = _build_search(sessions)

    # Default settings: hide claude-mem.
    out = s.search("")
    assert [r.id for r in out] == ["b"]


def test_search_includes_claude_mem_when_toggled(monkeypatch) -> None:
    home = str(Path.home())
    sessions = [
        _session("a", f"{home}/.claude-mem/observer-sessions"),
        _session("b", f"{home}/projects/normal"),
    ]
    s = _build_search(sessions)

    cfg = settings.current()
    cfg.filters.hide_claude_mem = False
    settings.update(cfg)

    out = s.search("")
    assert {r.id for r in out} == {"a", "b"}


def test_search_respects_hide_directories(monkeypatch) -> None:
    home = str(Path.home())
    sessions = [
        _session("a", f"{home}/throwaway/exp1"),
        _session("b", f"{home}/projects/normal"),
    ]
    s = _build_search(sessions)

    cfg = settings.current()
    cfg.filters.hide_claude_mem = False
    cfg.filters.hide_directories = [f"{home}/throwaway"]
    settings.update(cfg)

    out = s.search("")
    assert [r.id for r in out] == ["b"]


def test_session_count_subtracts_hidden(monkeypatch) -> None:
    home = str(Path.home())
    sessions = [
        _session("a", f"{home}/.claude-mem/observer-sessions"),
        _session("b", f"{home}/projects/normal"),
    ]
    s = _build_search(sessions)
    # Default hide_claude_mem=True → counter shows 1, not 2.
    assert s.get_session_count() == 1


def test_session_count_unchanged_when_nothing_hidden(monkeypatch) -> None:
    home = str(Path.home())
    sessions = [_session("a", f"{home}/projects/normal")]
    s = _build_search(sessions)
    assert s.get_session_count() == 1
