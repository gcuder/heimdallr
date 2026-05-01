"""Smoke tests for the TUI app: composition + resume action wiring.

These don't drive a full session through the app; they construct it,
mount it via Textual's Pilot, and verify the new bindings/handlers
behave as designed.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from heimdallr import settings
from heimdallr.models import RunningInfo, Session
from heimdallr.tui.app import HeimdallrApp


@pytest.fixture(autouse=True)
def isolate_settings(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "CONFIG_PATH", tmp_path / "config.toml")
    monkeypatch.setattr(settings, "_cached", None)
    yield


def _stub_search_engine(app: HeimdallrApp, sessions: list[Session]) -> None:
    """Bypass the real Tantivy/adapter pipeline so the TUI mounts cleanly."""
    fake = MagicMock()
    fake._sessions = sessions
    fake._sessions_by_id = {s.id: s for s in sessions}
    fake._streaming_in_progress = False
    fake._load_from_index.return_value = sessions
    fake.search.return_value = sessions
    fake.get_session_count.return_value = len(sessions)
    fake.get_agents_with_sessions.return_value = {"claude"}
    fake.get_resume_command.return_value = ["claude", "--resume", sessions[0].id]
    fake.get_adapter_for_session.return_value = MagicMock(supports_yolo=True)
    fake.adapters = []
    app.search_engine = fake


def _session(sid: str = "abc") -> Session:
    return Session(
        id=sid,
        agent="claude",
        title="Refactor TUI",
        directory="/Users/x/proj",
        timestamp=datetime.now() - timedelta(hours=1),
        content="» first prompt\n\n  reply",
        message_count=1,
        mtime=0.0,
    )


async def test_resume_spawns_new_terminal_and_stays_open() -> None:
    """Pressing Enter on a non-running session spawns a new terminal window
    and leaves hmd open — no modal, no exit."""
    app = HeimdallrApp()
    s = _session()
    _stub_search_engine(app, [s])

    with patch(
        "heimdallr.tui.app.spawn_new_terminal", return_value=True
    ) as spawn:
        async with app.run_test() as pilot:
            await pilot.pause()
            app.selected_session = s
            app._running_info = {}
            app.action_resume_session()
            await pilot.pause()
            # Spawned exactly once; no modal pushed; no fallback resume_command.
            spawn.assert_called_once()
            assert len(app.screen_stack) == 1
            assert app.get_resume_command() is None


async def test_resume_yolo_action_passes_yolo_true() -> None:
    app = HeimdallrApp()
    s = _session()
    _stub_search_engine(app, [s])

    with patch("heimdallr.tui.app.spawn_new_terminal", return_value=True):
        async with app.run_test() as pilot:
            await pilot.pause()
            app.selected_session = s
            app._running_info = {}
            app.action_resume_session_yolo()
            await pilot.pause()
            call = app.search_engine.get_resume_command.call_args
            assert call.kwargs.get("yolo") is True


async def test_resume_falls_back_to_cli_when_spawn_fails() -> None:
    """If spawn_new_terminal returns False (Linux, etc.), the app exits with
    a resume_command set so the CLI can os.execvp in the current shell."""
    app = HeimdallrApp()
    s = _session()
    _stub_search_engine(app, [s])

    with patch("heimdallr.tui.app.spawn_new_terminal", return_value=False):
        async with app.run_test() as pilot:
            await pilot.pause()
            app.selected_session = s
            app._running_info = {}
            app.action_resume_session()
            await pilot.pause()
            assert app.get_resume_command() == ["claude", "--resume", s.id]


async def test_resume_jumps_to_running_terminal_when_found() -> None:
    """If the session is running and we find a parent terminal, the app stays
    open and dispatches an activate() call instead of exiting."""
    app = HeimdallrApp()
    s = _session()
    _stub_search_engine(app, [s])

    fake_term = MagicMock(pid=4242, name="Terminal")
    with (
        patch("heimdallr.tui.app.find_terminal_pid", return_value=fake_term),
        patch("heimdallr.tui.app.activate_pid", return_value=(True, "ok")) as activate,
    ):
        async with app.run_test() as pilot:
            await pilot.pause()
            app.selected_session = s
            app._running_info = {
                s.id: RunningInfo(
                    is_running=True,
                    confidence="high",
                    pid=9999,
                    started_at=datetime.now(),
                    source=["self"],
                )
            }
            app.action_resume_session()
            await pilot.pause()
            activate.assert_called_once()
            assert app.get_resume_command() is None


async def test_running_session_falls_back_to_ide_when_terminal_missing() -> None:
    """If find_terminal_pid returns None but the session has an IDE attached,
    activate the IDE window — don't spawn a new terminal."""
    app = HeimdallrApp()
    s = _session()
    _stub_search_engine(app, [s])

    with (
        patch("heimdallr.tui.app.find_terminal_pid", return_value=None),
        patch("heimdallr.tui.app.activate_pid", return_value=(True, "ok")) as activate,
    ):
        async with app.run_test() as pilot:
            await pilot.pause()
            app.selected_session = s
            app._running_info = {
                s.id: RunningInfo(
                    is_running=True,
                    confidence="medium",
                    pid=9999,
                    ide="VS Code",
                    ide_pid=5555,
                    source=["psutil", "lock"],
                )
            }
            app.action_resume_session()
            await pilot.pause()
            activate.assert_called_once_with(5555, "VS Code")


async def test_running_session_does_not_spawn_when_jump_fails() -> None:
    """Critical: if the session is running but we can't find any window to
    jump to, hmd must stay open and NOT silently spawn a duplicate."""
    app = HeimdallrApp()
    s = _session()
    _stub_search_engine(app, [s])

    with (
        patch("heimdallr.tui.app.find_terminal_pid", return_value=None),
        patch("heimdallr.tui.app.activate_pid", return_value=(False, "no perm")),
    ):
        async with app.run_test() as pilot:
            await pilot.pause()
            app.selected_session = s
            app._running_info = {
                s.id: RunningInfo(
                    is_running=True,
                    confidence="medium",
                    pid=9999,
                    source=["psutil"],
                )
            }
            app.action_resume_session()
            await pilot.pause()
            # No resume command, no exit — hmd stays open.
            assert app.get_resume_command() is None
            assert len(app.screen_stack) == 1


async def test_toggle_claude_mem_persists_and_refreshes() -> None:
    app = HeimdallrApp()
    _stub_search_engine(app, [_session()])

    async with app.run_test() as pilot:
        await pilot.pause()
        # Default is hide_claude_mem=True.
        assert settings.current().filters.hide_claude_mem is True
        app.action_toggle_claude_mem()
        await pilot.pause()
        assert settings.current().filters.hide_claude_mem is False
        # Toggling again restores the hidden state.
        app.action_toggle_claude_mem()
        await pilot.pause()
        assert settings.current().filters.hide_claude_mem is True
