"""Claude Code session adapter."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Any

import orjson

from ..config import AGENTS, CLAUDE_DIR
from ..models import Session
from .base import BaseSessionAdapter, ErrorCallback, truncate_title


class ClaudeAdapter(BaseSessionAdapter):
    """Adapter for Claude Code sessions stored at ~/.claude/projects/*/*.jsonl."""

    name = "claude"
    color = AGENTS["claude"]["color"]
    badge = AGENTS["claude"]["badge"]
    supports_yolo = True

    def __init__(self, sessions_dir: Path | None = None) -> None:
        self._sessions_dir = sessions_dir if sessions_dir is not None else CLAUDE_DIR

    # ---- discovery ---------------------------------------------------------

    def find_sessions(self) -> list[Session]:
        if not self.is_available():
            return []
        sessions: list[Session] = []
        for project_dir in self._sessions_dir.iterdir():
            if not project_dir.is_dir():
                continue
            for session_file in project_dir.glob("*.jsonl"):
                if session_file.name.startswith("agent-"):
                    continue
                session = self._parse_session_file(session_file)
                if session:
                    sessions.append(session)
        return sessions

    def _scan_session_files(self) -> dict[str, tuple[Path, float]]:
        current: dict[str, tuple[Path, float]] = {}
        if not self._sessions_dir.exists():
            return current
        for project_dir in self._sessions_dir.iterdir():
            if not project_dir.is_dir():
                continue
            for session_file in project_dir.glob("*.jsonl"):
                if session_file.name.startswith("agent-"):
                    continue
                try:
                    mtime = session_file.stat().st_mtime
                except OSError:
                    continue
                current[session_file.stem] = (session_file, mtime)
        return current

    def _parse_session_file(
        self, session_file: Path, on_error: ErrorCallback = None
    ) -> Session | None:
        try:
            first_user_message = ""
            directory = ""
            timestamp = datetime.fromtimestamp(session_file.stat().st_mtime)
            messages: list[str] = []
            turn_count = 0

            with open(session_file, "rb") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        data = orjson.loads(line)
                    except orjson.JSONDecodeError:
                        continue

                    msg_type = data.get("type", "")

                    if msg_type == "user" and not directory:
                        directory = data.get("cwd", "")

                    if msg_type == "user":
                        msg = data.get("message", {})
                        content = msg.get("content", "")

                        is_human_input = False
                        if isinstance(content, str):
                            is_human_input = True
                            if not data.get("isMeta") and not content.startswith(
                                ("<command", "<local-command")
                            ):
                                messages.append(f"» {content}")
                                if not first_user_message and len(content) > 10:
                                    first_user_message = content
                        elif isinstance(content, list):
                            first_part = content[0] if content else {}
                            if isinstance(first_part, dict):
                                if first_part.get("type") == "text":
                                    is_human_input = True
                            for part in content:
                                if isinstance(part, dict) and part.get("type") == "text":
                                    text = part.get("text", "")
                                    messages.append(f"» {text}")
                                    if not first_user_message:
                                        first_user_message = text
                                elif isinstance(part, str):
                                    messages.append(f"» {part}")

                        if is_human_input:
                            turn_count += 1

                    if msg_type == "assistant":
                        msg = data.get("message", {})
                        content = msg.get("content", "")
                        has_text = False
                        if isinstance(content, str) and content:
                            messages.append(f"  {content}")
                            has_text = True
                        elif isinstance(content, list):
                            for part in content:
                                if isinstance(part, dict) and part.get("type") == "text":
                                    text = part.get("text", "")
                                    if text:
                                        messages.append(f"  {text}")
                                        has_text = True
                                elif isinstance(part, str):
                                    messages.append(f"  {part}")
                                    has_text = True
                        if has_text:
                            turn_count += 1

            if not first_user_message or not messages:
                return None

            return Session(
                id=session_file.stem,
                agent=self.name,
                title=truncate_title(first_user_message),
                directory=directory,
                timestamp=timestamp,
                content="\n\n".join(messages),
                message_count=turn_count,
            )
        except OSError as e:
            self._record_error(session_file, type(e).__name__, str(e), on_error)
            return None
        except (KeyError, TypeError, AttributeError) as e:
            self._record_error(session_file, type(e).__name__, str(e), on_error)
            return None

    # ---- execution ---------------------------------------------------------

    def get_resume_command(self, session: Session, yolo: bool = False) -> list[str]:
        cmd = ["claude"]
        if yolo:
            cmd.append("--dangerously-skip-permissions")
        cmd.extend(["--resume", session.id])
        return cmd

    def build_inject_command(
        self,
        ctx: str,
        target_id: str | None,
        cwd: str | None,
        method: str,
    ) -> list[str]:
        if method == "resume" and target_id:
            return ["claude", "--resume", target_id, "--append-system-prompt", ctx]
        if method == "file":
            ts = int(time.time())
            note = f"Read .heimdallr-context-{ts}.md and continue from where the previous session left off."
            return ["claude", "-p", note]
        # default: new session with context as prompt
        return ["claude", "-p", ctx]

    # ---- running detection -------------------------------------------------

    def process_match(self, proc: Any) -> tuple[str | None, str]:
        """Identify the session a Claude process is running.

        Returns (session_id, confidence). High confidence when --resume <sid> is in argv.
        Medium confidence is reserved for cwd-only matches and is resolved upstream
        because the adapter doesn't know about the session list.
        """
        try:
            cmdline = proc.info.get("cmdline") or []
        except Exception:
            return None, "medium"
        if not cmdline:
            return None, "medium"
        exe = Path(cmdline[0]).name
        if exe != "claude":
            return None, "medium"

        # high-confidence: --resume <sid>
        for i, arg in enumerate(cmdline):
            if arg == "--resume" and i + 1 < len(cmdline):
                return cmdline[i + 1], "high"
            if arg.startswith("--resume="):
                return arg.split("=", 1)[1], "high"

        # medium: bare claude — caller resolves via cwd
        return None, "medium"
