"""Tests for compactor + injector."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from heimdallr.models import Session
from heimdallr.transfer import build_inject_plan, compact, execute_plan


def _session(content: str = "", message_count: int = 4) -> Session:
    return Session(
        id="abc-123",
        agent="claude",
        title="Refactor the auth module",
        directory="/tmp/proj",
        timestamp=datetime.fromtimestamp(1700000000),
        content=content,
        message_count=message_count,
        mtime=1700000000.0,
    )


def test_summary_strategy_includes_first_user_message() -> None:
    s = _session(
        "» Please refactor auth\n\n  I'll start by examining the existing code\n\n"
        "» Now extract the JWT logic into a helper\n\n  Done — see the new module."
    )
    bundle = compact(s, "summary")
    assert "Refactor the auth module" in bundle.text
    assert "Please refactor auth" in bundle.text
    assert "Now extract the JWT logic" in bundle.text
    assert bundle.strategy == "summary"
    assert bundle.token_count > 0


def test_hybrid_includes_summary_and_recent_turns() -> None:
    msgs = []
    for i in range(10):
        msgs.append(f"» User question number {i}")
        msgs.append(f"  Assistant answer to question {i}")
    s = _session("\n\n".join(msgs), message_count=20)
    bundle = compact(s, "hybrid")
    # summary header still present
    assert "Refactor the auth module" in bundle.text
    # last turn pairs are present verbatim
    assert "» User question number 9" in bundle.text
    assert "Assistant answer to question 9" in bundle.text
    # earliest turn-pairs dropped from the verbatim tail (the summary header
    # may still mention "Initial ask: User question number 0", which is fine)
    assert "» User question number 0" not in bundle.text
    assert "Assistant answer to question 0" not in bundle.text


def test_full_strategy_returns_entire_transcript_when_small() -> None:
    s = _session("» small\n\n  reply")
    bundle = compact(s, "full")
    assert "small" in bundle.text
    assert "reply" in bundle.text


def test_full_strategy_caps_huge_transcripts() -> None:
    huge = "\n\n".join(f"» turn {i}\n\n  reply {i} " + ("xxxxxxxxxx " * 50) for i in range(2000))
    s = _session(huge, message_count=4000)
    bundle = compact(s, "full")
    # cap is 50_000 tokens; we should be at or under it
    from heimdallr.transfer.compactor import MAX_FULL_TOKENS

    assert bundle.token_count <= MAX_FULL_TOKENS + 100  # loose since header adds tokens
    assert "[truncated to keep context within budget]" in bundle.text


def test_build_inject_plan_uses_inline_for_small_bundle(tmp_path: Path) -> None:
    s = _session("» small\n\n  reply")
    bundle = compact(s, "summary")
    plan = build_inject_plan(bundle, target_agent="claude", target_session_id=None, cwd=str(tmp_path))
    assert plan.method == "new_with_prompt"
    assert plan.argv[0] == "claude"
    assert plan.argv[1] == "-p"
    assert plan.context_file is None


def test_build_inject_plan_resume_when_target_id_given(tmp_path: Path) -> None:
    s = _session("» x\n\n  y")
    bundle = compact(s, "summary")
    plan = build_inject_plan(bundle, target_agent="claude", target_session_id="other-456", cwd=str(tmp_path))
    assert plan.method == "resume"
    assert "--resume" in plan.argv
    assert "other-456" in plan.argv
    assert "--append-system-prompt" in plan.argv


def test_build_inject_plan_falls_back_to_file_for_large_bundle(tmp_path: Path) -> None:
    huge = "\n\n".join(f"» turn {i}\n\n  reply {i} " + ("xxxxxxxxxx " * 50) for i in range(500))
    s = _session(huge, message_count=1000)
    bundle = compact(s, "full")
    plan = build_inject_plan(bundle, target_agent="claude", target_session_id=None, cwd=str(tmp_path))
    assert plan.method == "file"
    assert plan.context_file is not None
    assert plan.context_file.parent == tmp_path


def test_execute_plan_writes_file_and_records_row(tmp_path: Path) -> None:
    s = _session("» x\n\n  y" * 5000)  # force file method
    bundle = compact(s, "full")
    plan = build_inject_plan(bundle, target_agent="codex", target_session_id=None, cwd=str(tmp_path))

    db_file = tmp_path / "state.db"
    # patch DB_PATH for execute_plan -> save_transfer_row
    from heimdallr.transfer import injector as inj

    original = inj.DB_PATH
    inj.DB_PATH = db_file
    try:
        execute_plan(plan)
    finally:
        inj.DB_PATH = original

    assert plan.context_file is not None
    assert plan.context_file.exists()
    assert "Refactor the auth module" in plan.context_file.read_text()

    from heimdallr.db import open_db

    db = open_db(db_file)
    transfers = list(db["transfers"].rows)
    assert len(transfers) == 1
    assert transfers[0]["target_agent"] == "codex"
    assert transfers[0]["strategy"] == "full"
