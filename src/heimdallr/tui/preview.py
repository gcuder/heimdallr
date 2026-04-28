"""Session preview pane — metadata header + message stream."""

from __future__ import annotations

import re
from io import StringIO

from rich.console import Console, Group, RenderableType
from rich.markup import escape as escape_markup
from rich.syntax import Syntax
from rich.text import Text
from textual.widgets import Static

from ..config import AGENTS
from ..models import RunningInfo, Session
from .utils import highlight_matches


class SessionPreview(Static):
    """Compact preview pane: metadata block + first ~8 messages."""

    MATCH_STYLE = "bold reverse"
    MAX_ASSISTANT_LINES: int | None = None
    CODE_BLOCK_PATTERN = re.compile(r"```(\w*)")

    def __init__(self) -> None:
        super().__init__("", id="preview")

    def update_preview(
        self,
        session: Session | None,
        query: str = "",
        running_info: RunningInfo | None = None,
    ) -> None:
        if session is None:
            self.update("")
            return
        self.update(self._build(session, query, running_info))

    def _build(
        self, session: Session, query: str, running_info: RunningInfo | None
    ) -> RenderableType:
        renderables: list[RenderableType] = []

        if running_info and running_info.is_running:
            header = Text()
            header.append("● ", style="bold #4ade80")
            since = running_info.started_at
            since_str = since.strftime("%H:%M") if since else "?"
            header.append(f"running since {since_str}", style="bold")
            if running_info.ide:
                header.append(f" · attached to {running_info.ide}", style="dim")
            if running_info.source:
                header.append(f"  [{', '.join(running_info.source)}]", style="dim")
            renderables.append(header)

        meta = Text()
        meta.append("Title: ", style="dim")
        meta.append(session.title, style="bold")
        renderables.append(meta)

        sub = Text()
        sub.append(f"Agent: {session.agent} · ", style="dim")
        sub.append(f"Turns: {session.message_count} · ", style="dim")
        if session.directory:
            sub.append(f"Dir: {session.directory}", style="dim")
        renderables.append(sub)

        renderables.append(Text("─── Preview ───", style="dim"))

        content = session.content
        preview_text = ""
        if query:
            ql = query.lower()
            cl = content.lower()
            best_pos = -1
            for term in ql.split():
                if not term:
                    continue
                pos = cl.find(term)
                if pos != -1 and (best_pos == -1 or pos < best_pos):
                    best_pos = pos
            if best_pos != -1:
                start = max(0, best_pos - 200)
                end = min(len(content), start + 5000)
                preview_text = content[start:end]
                if start > 0:
                    preview_text = "..." + preview_text
                if end < len(content):
                    preview_text += "..."
        if not preview_text:
            preview_text = content[:5000]
            if len(content) > 5000:
                preview_text += "..."

        agent_cfg = AGENTS.get(session.agent, {"color": "white", "badge": session.agent})

        body = Text()
        for msg in preview_text.split("\n\n"):
            msg = msg.rstrip()
            if not msg.strip():
                continue
            self._render_message(body, msg, query, msg.startswith("» "), agent_cfg)

        renderables.append(body)
        return Group(*renderables)

    def _render_message(
        self,
        out: Text,
        msg: str,
        query: str,
        is_user: bool,
        agent_cfg: dict[str, str],
    ) -> None:
        lines = msg.split("\n")
        if not is_user and self.MAX_ASSISTANT_LINES and len(lines) > self.MAX_ASSISTANT_LINES:
            lines = lines[: self.MAX_ASSISTANT_LINES] + ["..."]

        first_assistant_line = True
        i = 0
        while i < len(lines):
            line = lines[i]
            cb = self.CODE_BLOCK_PATTERN.match(line)
            if cb:
                language = cb.group(1) or ""
                code_lines: list[str] = []
                i += 1
                while i < len(lines) and not lines[i].startswith("```"):
                    code_lines.append(lines[i])
                    i += 1
                if code_lines:
                    self._render_code(out, "\n".join(code_lines), language)
                if i < len(lines) and lines[i].startswith("```"):
                    i += 1
                continue

            if line.startswith("» "):
                out.append("» ", style="bold cyan")
                content_part = escape_markup(line[2:])
                if len(content_part) > 200:
                    content_part = content_part[:200].rsplit(" ", 1)[0] + " ..."
                out.append_text(highlight_matches(content_part, query, style=self.MATCH_STYLE))
                out.append("\n")
            elif line == "...":
                out.append("   ⋯\n", style="dim")
            elif line.startswith("..."):
                out.append(escape_markup(line) + "\n", style="dim")
            elif line.startswith("  "):
                if first_assistant_line:
                    out.append("● ", style=agent_cfg["color"])
                    out.append(agent_cfg["badge"], style=f"bold {agent_cfg['color']}")
                    out.append(" ")
                    content = line.lstrip()
                    first_assistant_line = False
                else:
                    content = line
                out.append_text(
                    highlight_matches(escape_markup(content), query, style=self.MATCH_STYLE)
                )
                out.append("\n")
            else:
                out.append_text(
                    highlight_matches(escape_markup(line), query, style=self.MATCH_STYLE)
                )
                out.append("\n")
            i += 1

    def _render_code(self, out: Text, code: str, language: str) -> None:
        lang_map = {
            "js": "javascript",
            "ts": "typescript",
            "py": "python",
            "rb": "ruby",
            "sh": "bash",
            "yml": "yaml",
            "": "text",
        }
        language = lang_map.get(language, language) or "text"
        try:
            syntax = Syntax(
                code,
                language,
                theme="ansi_dark",
                line_numbers=False,
                word_wrap=True,
                background_color="default",
            )
            sio = StringIO()
            console = Console(file=sio, force_terminal=True, width=200)
            console.print(syntax, end="")
            for line in sio.getvalue().rstrip().split("\n"):
                out.append("  ")
                out.append_text(Text.from_ansi(line))
                out.append("\n")
        except Exception:
            for line in code.split("\n"):
                out.append("  " + escape_markup(line) + "\n", style="dim")
