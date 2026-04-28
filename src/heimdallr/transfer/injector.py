"""Build and execute a context-transfer command.

The injector decides whether to embed context inline (`--append-system-prompt`
for Claude, `codex resume <sid> <ctx>` for Codex) or to write a context file
to disk and reference it from a short prompt. The threshold is conservative
(4096 tokens) to stay below CLI argv length limits and shell quoting issues.
"""

from __future__ import annotations

import shlex
import time
from dataclasses import dataclass
from pathlib import Path

from ..adapters import get_adapter
from ..config import DB_PATH
from ..db import open_db
from .compactor import ContextBundle

# Inline injection is fine up to ~4k tokens; beyond that we drop to a CONTEXT file.
INLINE_TOKEN_LIMIT = 4096


@dataclass
class InjectPlan:
    argv: list[str]
    cwd: str
    target_agent: str
    target_session_id: str | None
    method: str  # "resume" | "new_with_prompt" | "new" | "file"
    context_file: Path | None  # only set when method == "file"
    bundle: ContextBundle


def build_inject_plan(
    bundle: ContextBundle,
    target_agent: str,
    target_session_id: str | None,
    cwd: str,
) -> InjectPlan:
    """Pick the best inject method for `target_agent` and build the argv."""
    adapter = get_adapter(target_agent)
    if adapter is None:
        raise ValueError(f"Unknown target agent: {target_agent}")

    # Decide method.
    if bundle.token_count > INLINE_TOKEN_LIMIT:
        method = "file"
    elif target_session_id:
        method = "resume"
    elif target_agent == "claude":
        method = "new_with_prompt"
    else:
        method = "new"  # codex

    context_file: Path | None = None
    if method == "file":
        ts = int(time.time())
        context_file = Path(cwd) / f".heimdallr-context-{ts}.md"

    argv = adapter.build_inject_command(
        ctx=bundle.text,
        target_id=target_session_id,
        cwd=cwd,
        method=method,
    )

    return InjectPlan(
        argv=argv,
        cwd=cwd,
        target_agent=target_agent,
        target_session_id=target_session_id,
        method=method,
        context_file=context_file,
        bundle=bundle,
    )


def materialize_context_file(plan: InjectPlan) -> None:
    """If the plan uses a CONTEXT file, write it to disk."""
    if plan.context_file is None:
        return
    plan.context_file.parent.mkdir(parents=True, exist_ok=True)
    plan.context_file.write_text(plan.bundle.text, encoding="utf-8")


def save_transfer_row(plan: InjectPlan, db_path: Path | None = None) -> int:
    """Persist a transfer audit row. Returns the new row id."""
    db = open_db(db_path or DB_PATH)
    row = db["transfers"].insert(
        {
            "source_session_id": plan.bundle.source_session_id,
            "target_session_id": plan.target_session_id or "",
            "source_agent": plan.bundle.source_agent,
            "target_agent": plan.target_agent,
            "strategy": plan.bundle.strategy,
            "method": plan.method,
            "compacted_text": plan.bundle.text,
            "token_count": plan.bundle.token_count,
            "command_used": shlex.join(plan.argv),
            "executed_at": int(time.time()),
        }
    )
    return int(row.last_pk) if row.last_pk is not None else -1


def execute_plan(plan: InjectPlan) -> None:
    """Side-effects only: write CONTEXT file, save audit row.

    Does NOT exec — the cli.py owns process replacement so the wrapper can run.
    """
    materialize_context_file(plan)
    save_transfer_row(plan)
