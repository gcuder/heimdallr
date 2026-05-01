"""Tests for find_terminal_pid (parent walk) and detect_terminal_app."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from heimdallr.running import terminal as term_mod


class FakeProc:
    def __init__(self, pid: int, name: str) -> None:
        self.pid = pid
        self._name = name

    def name(self) -> str:
        return self._name


def _patch_chain(parents: list[FakeProc]):
    """Patch psutil.Process(pid).parents() to return `parents`."""
    fake_root = MagicMock()
    fake_root.parents.return_value = parents
    return patch.object(term_mod.psutil, "Process", return_value=fake_root)


def test_walks_through_shell_to_find_terminal() -> None:
    chain = [
        FakeProc(2001, "zsh"),
        FakeProc(2002, "Terminal"),
        FakeProc(1, "launchd"),
    ]
    with _patch_chain(chain):
        ref = term_mod.find_terminal_pid(3000)
    assert ref is not None
    assert ref.pid == 2002
    assert ref.name == "Terminal"


def test_walks_through_tmux() -> None:
    chain = [
        FakeProc(2001, "zsh"),
        FakeProc(2002, "tmux: server"),
        FakeProc(2003, "iTerm2"),
    ]
    with _patch_chain(chain):
        ref = term_mod.find_terminal_pid(3000)
    assert ref is not None
    assert ref.name == "iTerm2"


def test_returns_none_when_no_terminal_in_chain() -> None:
    chain = [FakeProc(1, "launchd")]
    with _patch_chain(chain):
        ref = term_mod.find_terminal_pid(3000)
    assert ref is None


def test_returns_none_when_proc_lookup_fails() -> None:
    with patch.object(
        term_mod.psutil, "Process", side_effect=term_mod.psutil.NoSuchProcess(123)
    ):
        ref = term_mod.find_terminal_pid(123)
    assert ref is None


@pytest.mark.parametrize(
    ("term_program", "expected"),
    [
        ("Apple_Terminal", "Terminal"),
        ("iTerm.app", "iTerm"),
        ("WezTerm", "WezTerm"),
        ("ghostty", "Ghostty"),
        ("", "Terminal"),  # unknown -> default
    ],
)
def test_detect_terminal_app_maps_term_program(
    monkeypatch, term_program: str, expected: str
) -> None:
    monkeypatch.setenv("TERM_PROGRAM", term_program)
    assert term_mod.detect_terminal_app() == expected


def test_detect_terminal_app_honours_explicit_preference(monkeypatch) -> None:
    monkeypatch.setenv("TERM_PROGRAM", "Apple_Terminal")
    assert term_mod.detect_terminal_app(preferred="iTerm") == "iTerm"


@pytest.mark.skipif(sys.platform == "darwin", reason="darwin path tested via osascript")
def test_spawn_new_terminal_returns_false_on_non_darwin() -> None:
    assert term_mod.spawn_new_terminal("/tmp", ["echo", "hi"]) is False
