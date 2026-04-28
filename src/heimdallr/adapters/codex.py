"""Codex CLI session adapter."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Any

import orjson

from ..config import AGENTS, CODEX_DIR
from ..models import Session
from .base import BaseSessionAdapter, ErrorCallback, truncate_title


class CodexAdapter(BaseSessionAdapter):
    """Adapter for Codex CLI sessions at ~/.codex/sessions/YYYY/MM/DD/*.jsonl."""

    name = "codex"
    color = AGENTS["codex"]["color"]
    badge = AGENTS["codex"]["badge"]
    supports_yolo = True

    def __init__(self, sessions_dir: Path | None = None) -> None:
        self._sessions_dir = sessions_dir if sessions_dir is not None else CODEX_DIR

    # ---- discovery ---------------------------------------------------------

    def find_sessions(self) -> list[Session]:
        if not self.is_available():
            return []
        sessions: list[Session] = []
        for session_file in self._sessions_dir.rglob("*.jsonl"):
            session = self._parse_session_file(session_file)
            if session:
                sessions.append(session)
        return sessions

    def _scan_session_files(self) -> dict[str, tuple[Path, float]]:
        current: dict[str, tuple[Path, float]] = {}
        if not self._sessions_dir.exists():
            return current
        for session_file in self._sessions_dir.rglob("*.jsonl"):
            try:
                mtime = session_file.stat().st_mtime
            except OSError:
                continue
            current[self._extract_id(session_file)] = (session_file, mtime)
        return current

    def _extract_id(self, session_file: Path) -> str:
        """Read session_meta to get the canonical id; fall back to filename stem."""
        try:
            with open(session_file, "rb") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        data = orjson.loads(line)
                    except orjson.JSONDecodeError:
                        continue
                    if data.get("type") == "session_meta":
                        sid = data.get("payload", {}).get("id", "")
                        if sid:
                            return sid
                        break
        except OSError:
            pass
        stem = session_file.stem
        return stem.split("-", 1)[-1] if "-" in stem else stem

    def _parse_session_file(
        self, session_file: Path, on_error: ErrorCallback = None
    ) -> Session | None:
        try:
            session_id = ""
            directory = ""
            timestamp = datetime.fromtimestamp(session_file.stat().st_mtime)
            messages: list[str] = []
            user_prompts: list[str] = []
            turn_count = 0
            yolo = False

            with open(session_file, "rb") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        data = orjson.loads(line)
                    except orjson.JSONDecodeError:
                        continue

                    msg_type = data.get("type", "")
                    payload = data.get("payload", {})

                    if msg_type == "session_meta":
                        session_id = payload.get("id", "")
                        directory = payload.get("cwd", "")

                    if msg_type == "turn_context":
                        approval_policy = payload.get("approval_policy", "")
                        sandbox_policy = payload.get("sandbox_policy", {})
                        sandbox_mode = (
                            sandbox_policy.get("mode", "")
                            if isinstance(sandbox_policy, dict)
                            else ""
                        )
                        if approval_policy == "never" or sandbox_mode == "danger-full-access":
                            yolo = True

                    if msg_type == "response_item":
                        role = payload.get("role", "")
                        content = payload.get("content", [])
                        if role in ("user", "assistant"):
                            role_prefix = "» " if role == "user" else "  "
                            has_text = False
                            for part in content:
                                if isinstance(part, dict):
                                    text = part.get("text", "") or part.get("input_text", "")
                                    if text and not text.strip().startswith(
                                        "<environment_context>"
                                    ):
                                        messages.append(f"{role_prefix}{text}")
                                        has_text = True
                            if has_text:
                                turn_count += 1

                    if msg_type == "event_msg":
                        event_type = payload.get("type", "")
                        if event_type == "user_message":
                            msg = payload.get("message", "")
                            if msg:
                                messages.append(f"» {msg}")
                                user_prompts.append(msg)
                        elif event_type == "agent_reasoning":
                            text = payload.get("text", "")
                            if text:
                                messages.append(f"  {text}")

            if not session_id:
                stem = session_file.stem
                session_id = stem.split("-", 1)[-1] if "-" in stem else stem

            if not user_prompts:
                return None

            return Session(
                id=session_id,
                agent=self.name,
                title=truncate_title(user_prompts[0], max_length=80, word_break=False),
                directory=directory,
                timestamp=timestamp,
                content="\n\n".join(messages),
                message_count=turn_count,
                yolo=yolo,
            )
        except OSError as e:
            self._record_error(session_file, type(e).__name__, str(e), on_error)
            return None
        except (KeyError, TypeError, AttributeError) as e:
            self._record_error(session_file, type(e).__name__, str(e), on_error)
            return None

    # ---- execution ---------------------------------------------------------

    def get_resume_command(self, session: Session, yolo: bool = False) -> list[str]:
        cmd = ["codex"]
        if yolo:
            cmd.append("--dangerously-bypass-approvals-and-sandbox")
        cmd.extend(["resume", session.id])
        return cmd

    def build_inject_command(
        self,
        ctx: str,
        target_id: str | None,
        cwd: str | None,
        method: str,
    ) -> list[str]:
        if method == "resume" and target_id:
            return ["codex", "resume", target_id, ctx]
        if method == "file":
            ts = int(time.time())
            note = f"Read .heimdallr-context-{ts}.md and continue."
            return ["codex", "exec", note]
        return ["codex", "exec", ctx]

    # ---- running detection -------------------------------------------------

    def process_match(self, proc: Any) -> tuple[str | None, str]:
        try:
            cmdline = proc.info.get("cmdline") or []
        except Exception:
            return None, "medium"
        if not cmdline:
            return None, "medium"
        exe = Path(cmdline[0]).name
        if exe != "codex":
            return None, "medium"

        # high-confidence: `codex resume <sid>`
        for i, arg in enumerate(cmdline):
            if arg == "resume" and i + 1 < len(cmdline):
                candidate = cmdline[i + 1]
                if not candidate.startswith("-"):
                    return candidate, "high"

        return None, "medium"
