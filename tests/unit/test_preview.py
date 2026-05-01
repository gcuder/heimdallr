"""Tests for the structured session preview."""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from io import StringIO

from rich.console import Console

from heimdallr.models import RunningInfo, Session
from heimdallr.tui.preview import (
    SessionPreview,
    _compute_metrics,
    _first_user_block,
    _last_exchange,
)


def _render(preview: SessionPreview, session: Session, query: str = "", running: RunningInfo | None = None) -> str:
    sio = StringIO()
    console = Console(file=sio, force_terminal=False, width=120, color_system=None)
    console.print(preview._build(session, query, running), end="")
    return sio.getvalue()


def _session(content: str, *, directory: str = "/Users/x/proj", title: str = "Refactor TUI") -> Session:
    return Session(
        id="abc12345",
        agent="claude",
        title=title,
        directory=directory,
        timestamp=datetime.now() - timedelta(hours=3),
        content=content,
        message_count=2,
        mtime=time.time() - 60,
    )


def test_first_user_block_returns_first_prompt() -> None:
    content = "» first prompt\n\n  asst reply\n\n» second prompt"
    assert _first_user_block(content) == "first prompt"


def test_first_user_block_handles_empty() -> None:
    assert _first_user_block("") == ""


def test_last_exchange_walks_from_end() -> None:
    content = (
        "» initial\n\n  hello\n\n"
        "» middle question\n\n  middle answer\n\n"
        "» last question\n\n  last answer"
    )
    user, asst = _last_exchange(content)
    assert user == "last question"
    assert asst == "last answer"


def test_last_exchange_assistant_lines_dedented() -> None:
    content = "» q\n\n  line one\n  line two"
    _, asst = _last_exchange(content)
    assert asst == "line one\nline two"


def test_compute_metrics_counts_blocks() -> None:
    content = (
        "» one\n\n  reply with code\n\n```python\nprint(1)\n```\n\n"
        "» two\n\n  another"
    )
    m = _compute_metrics(_session(content))
    assert m.user_turns == 2
    assert m.assistant_turns == 2
    # One paired ``` fence = one code block.
    assert m.code_blocks == 1


def test_render_includes_required_sections() -> None:
    p = SessionPreview()
    s = _session("» first\n\n  reply\n\n» second\n\n  final")
    out = _render(p, s)
    assert "Refactor TUI" in out
    assert "Initial prompt" in out
    assert "Latest exchange" in out
    # The latest user turn should be in output (not the initial one).
    assert "second" in out


def test_render_shows_running_pill_with_elapsed() -> None:
    p = SessionPreview()
    s = _session("» q\n\n  a")
    info = RunningInfo(
        is_running=True,
        confidence="high",
        pid=42,
        started_at=datetime.now() - timedelta(minutes=15),
        source=["self"],
    )
    out = _render(p, s, running=info)
    assert "running" in out
    assert "15m" in out  # _humanize_delta should produce "15m"


def test_render_shows_idle_when_not_running() -> None:
    p = SessionPreview()
    s = _session("» q\n\n  a")
    out = _render(p, s)
    assert "idle" in out


def test_render_query_excerpt_appears_when_match() -> None:
    p = SessionPreview()
    content = "» talking about widgets\n\n  the widget framework is nice"
    s = _session(content)
    out = _render(p, s, query="framework")
    assert "Match in transcript" in out


def test_render_query_excerpt_skipped_when_no_match() -> None:
    p = SessionPreview()
    s = _session("» nothing here\n\n  reply")
    out = _render(p, s, query="zzznotmatched")
    assert "Match in transcript" not in out
