"""Tests for the TOML settings layer."""

from __future__ import annotations

from pathlib import Path

from heimdallr import settings


def _stub_path(monkeypatch, tmp_path: Path) -> Path:
    p = tmp_path / "config.toml"
    monkeypatch.setattr(settings, "CONFIG_PATH", p)
    monkeypatch.setattr(settings, "_cached", None)
    return p


def test_load_returns_defaults_when_file_missing(monkeypatch, tmp_path) -> None:
    _stub_path(monkeypatch, tmp_path)
    s = settings.load()
    # Default protects users from claude-mem flooding their list.
    assert s.filters.hide_claude_mem is True
    assert s.filters.hide_directories == []
    assert s.resume.terminal == ""


def test_save_then_load_roundtrip(monkeypatch, tmp_path) -> None:
    _stub_path(monkeypatch, tmp_path)
    s = settings.Settings()
    s.filters.hide_claude_mem = False
    s.filters.hide_directories = ["~/throwaway", "/tmp/bench"]
    s.resume.terminal = "iTerm"

    settings.save(s)
    out = settings.load()
    assert out.filters.hide_claude_mem is False
    assert out.filters.hide_directories == ["~/throwaway", "/tmp/bench"]
    assert out.resume.terminal == "iTerm"


def test_load_tolerates_malformed_file(monkeypatch, tmp_path) -> None:
    p = _stub_path(monkeypatch, tmp_path)
    p.write_text("this is not [valid TOML at all\n")
    s = settings.load()
    # Garbage in → defaults out, no exception.
    assert s.filters.hide_claude_mem is True


def test_hidden_prefixes_includes_claude_mem(monkeypatch, tmp_path) -> None:
    _stub_path(monkeypatch, tmp_path)
    s = settings.Settings()
    prefixes = s.hidden_prefixes()
    assert any(p.endswith(".claude-mem") for p in prefixes)


def test_hidden_prefixes_expands_user_home(monkeypatch, tmp_path) -> None:
    _stub_path(monkeypatch, tmp_path)
    s = settings.Settings()
    s.filters.hide_claude_mem = False
    s.filters.hide_directories = ["~/throwaway"]
    prefixes = s.hidden_prefixes()
    assert prefixes
    # ~ must be expanded so prefix matching works against absolute paths.
    assert all("~" not in p for p in prefixes)


def test_hide_claude_mem_false_excludes_default_prefix(monkeypatch, tmp_path) -> None:
    _stub_path(monkeypatch, tmp_path)
    s = settings.Settings()
    s.filters.hide_claude_mem = False
    assert s.hidden_prefixes() == []


def test_update_persists_and_caches(monkeypatch, tmp_path) -> None:
    _stub_path(monkeypatch, tmp_path)
    s = settings.current()  # primes cache with defaults
    s.filters.hide_claude_mem = False
    settings.update(s)
    # Cache reflects the update without a reload.
    assert settings.current().filters.hide_claude_mem is False
    # Disk reflects the update.
    assert "hide_claude_mem = false" in settings.CONFIG_PATH.read_text()


def test_full_roundtrip_all_sections(monkeypatch, tmp_path) -> None:
    _stub_path(monkeypatch, tmp_path)
    s = settings.Settings()
    s.display.theme = "nord"
    s.display.show_logo = False
    s.display.sort_mode = "running"
    s.display.show_preview = False
    s.filters.default_agent = "claude"
    s.filters.default_view = "running"
    s.resume.yolo_default = True
    s.resume.prefer_ide = True
    s.transfer.target_ide = "Cursor"
    s.notifications.default_timeout_s = 1.5
    s.notifications.error_timeout_s = 8.0
    s.notifications.auto_dismiss_errors = False
    s.keybindings.overrides = {"resume_session": "ctrl+enter", "settings": "comma"}

    settings.save(s)
    out = settings.load()
    assert out.display.theme == "nord"
    assert out.display.show_logo is False
    assert out.display.sort_mode == "running"
    assert out.display.show_preview is False
    assert out.filters.default_agent == "claude"
    assert out.filters.default_view == "running"
    assert out.resume.yolo_default is True
    assert out.resume.prefer_ide is True
    assert out.transfer.target_ide == "Cursor"
    assert out.notifications.default_timeout_s == 1.5
    assert out.notifications.error_timeout_s == 8.0
    assert out.notifications.auto_dismiss_errors is False
    assert out.keybindings.overrides == {
        "resume_session": "ctrl+enter",
        "settings": "comma",
    }


def test_default_agent_blank_means_all(monkeypatch, tmp_path) -> None:
    _stub_path(monkeypatch, tmp_path)
    s = settings.Settings()
    # Empty string in TOML reads back as None (== "all agents")
    settings.save(s)
    assert settings.load().filters.default_agent is None


def test_reset_section_replaces_only_targeted_section(monkeypatch, tmp_path) -> None:
    _stub_path(monkeypatch, tmp_path)
    s = settings.current()
    s.display.theme = "dracula"
    s.filters.hide_claude_mem = False
    settings.update(s)

    settings.reset_section("display")

    fresh = settings.current()
    assert fresh.display.theme == "textual-dark"  # reset
    assert fresh.filters.hide_claude_mem is False  # untouched
