"""Adapter parsing tests — Claude + Codex JSONL → Session."""

from __future__ import annotations

from pathlib import Path

from heimdallr.adapters import ClaudeAdapter, CodexAdapter


def test_claude_finds_session_and_skips_agent_files(claude_session_dir: Path) -> None:
    adapter = ClaudeAdapter(sessions_dir=claude_session_dir)
    sessions = adapter.find_sessions()

    assert len(sessions) == 1
    s = sessions[0]
    assert s.id == "11111111-1111-1111-1111-111111111111"
    assert s.agent == "claude"
    assert s.directory == "/Users/test/myproject"
    assert "Hello from a test" in s.title
    assert s.message_count == 4  # 2 user + 2 assistant turns


def test_claude_resume_command(claude_session_dir: Path) -> None:
    adapter = ClaudeAdapter(sessions_dir=claude_session_dir)
    s = adapter.find_sessions()[0]

    assert adapter.get_resume_command(s) == ["claude", "--resume", s.id]
    assert adapter.get_resume_command(s, yolo=True) == [
        "claude",
        "--dangerously-skip-permissions",
        "--resume",
        s.id,
    ]


def test_claude_inject_commands(claude_session_dir: Path) -> None:
    adapter = ClaudeAdapter(sessions_dir=claude_session_dir)
    sid = "abcd"
    assert adapter.build_inject_command("hello", sid, None, "resume") == [
        "claude",
        "--resume",
        sid,
        "--append-system-prompt",
        "hello",
    ]
    new = adapter.build_inject_command("ctx", None, None, "new_with_prompt")
    assert new[:2] == ["claude", "-p"]


def test_claude_process_match() -> None:
    adapter = ClaudeAdapter()

    class FakeProc:
        info = {"cmdline": ["claude", "--resume", "abc-123"]}

    sid, conf = adapter.process_match(FakeProc())
    assert sid == "abc-123"
    assert conf == "high"

    class BareProc:
        info = {"cmdline": ["claude"]}

    sid, conf = adapter.process_match(BareProc())
    assert sid is None
    assert conf == "medium"


def test_codex_finds_session(codex_session_dir: Path) -> None:
    adapter = CodexAdapter(sessions_dir=codex_session_dir)
    sessions = adapter.find_sessions()

    assert len(sessions) == 1
    s = sessions[0]
    assert s.id == "22222222-2222-2222-2222-222222222222"
    assert s.agent == "codex"
    assert s.directory == "/Users/test/api"
    assert "Investigate the crash" in s.title


def test_codex_resume_command(codex_session_dir: Path) -> None:
    adapter = CodexAdapter(sessions_dir=codex_session_dir)
    s = adapter.find_sessions()[0]
    assert adapter.get_resume_command(s) == ["codex", "resume", s.id]
    assert adapter.get_resume_command(s, yolo=True) == [
        "codex",
        "--dangerously-bypass-approvals-and-sandbox",
        "resume",
        s.id,
    ]


def test_codex_process_match() -> None:
    adapter = CodexAdapter()

    class FakeProc:
        info = {"cmdline": ["codex", "resume", "xyz-9"]}

    sid, conf = adapter.process_match(FakeProc())
    assert sid == "xyz-9"
    assert conf == "high"


def test_incremental_skip_unchanged(claude_session_dir: Path) -> None:
    adapter = ClaudeAdapter(sessions_dir=claude_session_dir)
    sessions = adapter.find_sessions()
    assert len(sessions) == 1
    sid = sessions[0].id

    # Pretend index already has this session at its current mtime
    files = adapter._scan_session_files()
    mtime = files[sid][1]
    known = {sid: (mtime, "claude")}

    new_or_modified, deleted = adapter.find_sessions_incremental(known)
    assert new_or_modified == []
    assert deleted == []
