"""Shared test fixtures."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest


def _write_jsonl(path: Path, lines: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")


@pytest.fixture
def claude_session_dir(tmp_path: Path) -> Path:
    """Build a fake ~/.claude/projects/<proj>/<id>.jsonl tree."""
    project = tmp_path / "claude" / "projects" / "-Users-test-myproject"
    session_id = "11111111-1111-1111-1111-111111111111"
    _write_jsonl(
        project / f"{session_id}.jsonl",
        [
            {
                "type": "user",
                "cwd": "/Users/test/myproject",
                "message": {"content": "Hello from a test, please help me debug"},
            },
            {
                "type": "assistant",
                "message": {"content": "Sure, what is the issue?"},
            },
            {
                "type": "user",
                "cwd": "/Users/test/myproject",
                "message": {"content": "The function returns None unexpectedly."},
            },
            {
                "type": "assistant",
                "message": {"content": "That usually means a missing return statement."},
            },
        ],
    )
    # An agent-* file that should be skipped
    _write_jsonl(
        project / "agent-skip-me.jsonl",
        [{"type": "user", "message": {"content": "ignore me"}}],
    )
    return tmp_path / "claude" / "projects"


@pytest.fixture
def codex_session_dir(tmp_path: Path) -> Path:
    """Build a fake ~/.codex/sessions/YYYY/MM/DD/<file>.jsonl tree."""
    today = datetime.now()
    base = tmp_path / "codex" / "sessions" / today.strftime("%Y") / today.strftime("%m") / today.strftime("%d")
    session_id = "22222222-2222-2222-2222-222222222222"
    _write_jsonl(
        base / f"rollout-{session_id}.jsonl",
        [
            {
                "type": "session_meta",
                "payload": {"id": session_id, "cwd": "/Users/test/api"},
            },
            {
                "type": "turn_context",
                "payload": {
                    "approval_policy": "on-request",
                    "sandbox_policy": {"mode": "workspace-write"},
                },
            },
            {
                "type": "event_msg",
                "payload": {
                    "type": "user_message",
                    "message": "Investigate the crash on startup",
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "role": "assistant",
                    "content": [{"text": "Looking at the trace now."}],
                },
            },
        ],
    )
    return tmp_path / "codex" / "sessions"
