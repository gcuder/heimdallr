"""Smoke tests for the SettingsModal.

These don't drive every control — they verify the modal mounts cleanly,
core toggles persist + broadcast, and Escape only closes the modal.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from heimdallr import settings
from heimdallr.models import Session
from heimdallr.tui.app import HeimdallrApp
from heimdallr.tui.settings_modal import SettingsModal


@pytest.fixture(autouse=True)
def isolate_settings(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "CONFIG_PATH", tmp_path / "config.toml")
    monkeypatch.setattr(settings, "_cached", None)
    yield


def _stub_search_engine(app: HeimdallrApp) -> None:
    s = Session(
        id="abc",
        agent="claude",
        title="t",
        directory="/x",
        timestamp=datetime.now() - timedelta(hours=1),
        content="» hi\n\n  ho",
        message_count=1,
        mtime=0.0,
    )
    fake = MagicMock()
    fake._sessions = [s]
    fake._sessions_by_id = {s.id: s}
    fake._streaming_in_progress = False
    fake._load_from_index.return_value = [s]
    fake.search.return_value = [s]
    fake.get_session_count.return_value = 1
    fake.get_agents_with_sessions.return_value = {"claude"}
    fake.adapters = []
    app.search_engine = fake


async def test_settings_modal_opens_via_keybinding() -> None:
    app = HeimdallrApp()
    _stub_search_engine(app)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("escape")  # defocus search
        await pilot.press("s")
        await pilot.pause()
        assert any(isinstance(s, SettingsModal) for s in app.screen_stack)


async def test_settings_modal_dismisses_with_escape_keeps_app_open() -> None:
    app = HeimdallrApp()
    _stub_search_engine(app)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.push_screen(SettingsModal())
        await pilot.pause()
        assert any(isinstance(s, SettingsModal) for s in app.screen_stack)
        await pilot.press("escape")
        await pilot.pause()
        # Modal popped, app still alive.
        assert not any(isinstance(s, SettingsModal) for s in app.screen_stack)
        assert app.is_running


async def test_app_seeds_reactives_from_settings(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(settings, "CONFIG_PATH", tmp_path / "config.toml")
    s = settings.Settings()
    s.display.theme = "nord"
    s.display.sort_mode = "pinned"
    s.display.show_preview = False
    s.filters.default_view = "running"
    settings.update(s)

    app = HeimdallrApp()
    assert app.theme == "nord"
    assert app.sort_mode == "pinned"
    assert app.show_preview is False
    assert app.active_view == "running"


async def test_modal_toggle_persists_to_disk() -> None:
    """Mount the modal directly and flip the hide_claude_mem switch."""
    app = HeimdallrApp()
    _stub_search_engine(app)
    async with app.run_test() as pilot:
        await pilot.pause()
        modal = SettingsModal()
        app.push_screen(modal)
        await pilot.pause()

        # Find the switch widget and flip it.
        from textual.widgets import Switch

        switch = modal.query_one("#filters-hide-mem", Switch)
        switch.value = not switch.value
        await pilot.pause()

        # Settings file should reflect the new value.
        text = settings.CONFIG_PATH.read_text()
        assert "hide_claude_mem = false" in text or "hide_claude_mem = true" in text
        # And the cached settings agree with the switch value.
        assert settings.current().filters.hide_claude_mem == switch.value
