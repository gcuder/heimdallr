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
