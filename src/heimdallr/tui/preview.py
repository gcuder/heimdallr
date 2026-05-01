"""Session preview pane — structured summary with metrics and timeline.

The pane is the dominant area of the TUI; the list above is just an entry
point. Each session is rendered as five labelled blocks:

  1. Header     — title + running/idle pill + duration since started
  2. Identity   — agent / directory / session id
  3. Activity   — turn counts, code blocks, age, last activity
  4. Initial    — the first user prompt, indented
  5. Latest     — last user/assistant exchange, plus a query-match excerpt
                  when a search term is active
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime
from io import StringIO

import humanize
from rich.console import Console, Group, RenderableType
from rich.markup import escape as escape_markup
from rich.rule import Rule
from rich.syntax import Syntax
from rich.text import Text
from textual.widgets import Static

from .. import bookmarks
from ..config import AGENTS
from ..models import RunningInfo, Session
from .utils import highlight_matches


class SessionPreview(Static):
    """Structured session summary — header, identity, metrics, prompt, latest."""

    MATCH_STYLE = "bold reverse"
    CODE_BLOCK_PATTERN = re.compile(r"```(\w*)")
    INITIAL_MAX_LINES = 5
    LATEST_MAX_LINES = 12
    QUERY_EXCERPT_CHARS = 1000

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

    # ---- top-level layout ------------------------------------------------

    def _build(
        self, session: Session, query: str, running_info: RunningInfo | None
    ) -> RenderableType:
        agent_cfg = AGENTS.get(
            session.agent, {"color": "white", "badge": session.agent}
        )
        renderables: list[RenderableType] = []

        renderables.append(self._render_header(session, running_info, agent_cfg))
        renderables.append(self._render_identity(session, agent_cfg))
        renderables.append(Rule(style="dim"))
        renderables.append(self._render_activity(session))
        renderables.append(Rule(style="dim"))
        renderables.append(_section_label("Initial prompt"))
        renderables.append(self._render_initial(session, query))
        renderables.append(Rule(style="dim"))
        renderables.append(_section_label("Latest exchange"))
        renderables.append(self._render_latest(session, query, agent_cfg))

        if query:
            excerpt = self._render_query_excerpt(session, query)
            if excerpt is not None:
                renderables.append(Rule(style="dim"))
                renderables.append(_section_label("Match in transcript"))
                renderables.append(excerpt)

        return Group(*renderables)

    # ---- block 1: header -------------------------------------------------

    def _render_header(
        self,
        session: Session,
        running_info: RunningInfo | None,
        agent_cfg: dict[str, str],
    ) -> Text:
        line = Text()
        is_running = bool(running_info and running_info.is_running)
        if is_running:
            line.append("● ", style="bold #4ade80")
        else:
            line.append("○ ", style="dim")
        line.append(session.title or "(untitled)", style="bold")
        line.append("   ")
        if is_running:
            line.append("running", style="bold #4ade80")
            since = running_info.started_at if running_info else None
            if since is not None:
                elapsed = datetime.now() - since
                line.append(f" · {_humanize_delta(elapsed)}", style="#4ade80")
            if running_info and running_info.ide:
                line.append(f" · {running_info.ide}", style="dim")
        else:
            line.append("idle", style="dim")
        return line

    # ---- block 2: identity -----------------------------------------------

    def _render_identity(
        self, session: Session, agent_cfg: dict[str, str]
    ) -> Text:
        line = Text()
        line.append(agent_cfg["badge"], style=f"bold {agent_cfg['color']}")
        line.append(" · ", style="dim")
        line.append(_pretty_path(session.directory) or "(no cwd)", style="dim")
        line.append(" · ", style="dim")
        line.append(session.id[:8], style="dim")
        if session.yolo:
            line.append("  yolo", style="bold #facc15")
        return line

    # ---- block 3: activity metrics --------------------------------------

    def _render_activity(self, session: Session) -> Text:
        metrics = _compute_metrics(session)

        line = Text()
        line.append(f"{metrics.user_turns} user", style="bold")
        line.append(" · ", style="dim")
        line.append(f"{metrics.assistant_turns} asst", style="bold")
        line.append(" · ", style="dim")
        line.append(f"{metrics.code_blocks} code blocks")
        line.append(" · ", style="dim")
        line.append(f"{metrics.total_chars:,} chars")
        line.append("\n")

        line.append(f"started {humanize.naturaltime(session.timestamp)}", style="dim")
        if session.mtime:
            last = datetime.fromtimestamp(session.mtime)
            line.append(" · ", style="dim")
            line.append(f"last activity {humanize.naturaltime(last)}", style="dim")
        if session.id in bookmarks.get_pinned_ids():
            line.append("  ★ pinned", style="#f59e0b")
        return line

    # ---- block 4: initial prompt ----------------------------------------

    def _render_initial(self, session: Session, query: str) -> Text:
        first = _first_user_block(session.content)
        if not first:
            t = Text()
            t.append("(no prompt found)", style="dim italic")
            return t
        return _indented_text(first, query, max_lines=self.INITIAL_MAX_LINES)

    # ---- block 5: latest exchange ---------------------------------------

    def _render_latest(
        self, session: Session, query: str, agent_cfg: dict[str, str]
    ) -> Text:
        user_msg, assistant_msg = _last_exchange(session.content)
        out = Text()
        if user_msg:
            out.append("» ", style="bold cyan")
            out.append_text(
                _truncate_lines(user_msg, query, self.LATEST_MAX_LINES // 2)
            )
            out.append("\n")
        if assistant_msg:
            out.append("● ", style=agent_cfg["color"])
            out.append(agent_cfg["badge"], style=f"bold {agent_cfg['color']}")
            out.append(" ")
            out.append_text(
                _truncate_lines(
                    assistant_msg, query, self.LATEST_MAX_LINES - (1 if user_msg else 0)
                )
            )
        if not user_msg and not assistant_msg:
            out.append("(no messages)", style="dim italic")
        return out

    # ---- block 6: query excerpt -----------------------------------------

    def _render_query_excerpt(
        self, session: Session, query: str
    ) -> RenderableType | None:
        content = session.content
        ql = query.lower()
        cl = content.lower()
        best_pos = -1
        for term in ql.split():
            if not term:
                continue
            pos = cl.find(term)
            if pos != -1 and (best_pos == -1 or pos < best_pos):
                best_pos = pos
        if best_pos == -1:
            return None
        start = max(0, best_pos - 200)
        end = min(len(content), start + self.QUERY_EXCERPT_CHARS)
        excerpt = content[start:end]
        if start > 0:
            excerpt = "…" + excerpt
        if end < len(content):
            excerpt = excerpt + "…"
        out = Text()
        out.append_text(
            highlight_matches(escape_markup(excerpt), query, style=self.MATCH_STYLE)
        )
        return out


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------


def _section_label(label: str) -> Text:
    t = Text()
    t.append(label, style="dim italic")
    return t


def _pretty_path(p: str) -> str:
    if not p:
        return ""
    home = os.path.expanduser("~")
    if p.startswith(home):
        return "~" + p[len(home):]
    return p


def _humanize_delta(delta) -> str:
    """Compact 'Xh Ym' / 'Ym Zs' for live elapsed time."""
    total = max(0, int(delta.total_seconds()))
    if total < 60:
        return f"{total}s"
    if total < 3600:
        return f"{total // 60}m"
    h = total // 3600
    m = (total % 3600) // 60
    return f"{h}h {m}m" if m else f"{h}h"


def _first_user_block(content: str) -> str:
    """Return the first '» ...' block from content, with the » stripped."""
    if not content:
        return ""
    for chunk in content.split("\n\n"):
        if chunk.startswith("» "):
            return chunk[2:]
    return ""


def _last_exchange(content: str) -> tuple[str, str]:
    """Return (last_user_message, last_assistant_message). Either may be empty.

    The Claude/Codex adapters emit messages joined with '\\n\\n' where user
    blocks start with '» ' and assistant blocks start with two spaces. We
    walk from the end to find the most recent of each.
    """
    if not content:
        return "", ""
    chunks = content.split("\n\n")
    user_msg = ""
    asst_msg = ""
    for chunk in reversed(chunks):
        if chunk.startswith("» ") and not user_msg:
            user_msg = chunk[2:]
        elif chunk.startswith("  ") and not asst_msg:
            asst_msg = "\n".join(line.lstrip() for line in chunk.split("\n"))
        if user_msg and asst_msg:
            break
    return user_msg, asst_msg


def _truncate_lines(text: str, query: str, max_lines: int) -> Text:
    """Render text as Rich Text with at most `max_lines`, with query highlight."""
    out = Text()
    lines = text.split("\n")
    truncated = lines[:max_lines]
    for i, line in enumerate(truncated):
        out.append_text(
            highlight_matches(
                escape_markup(line), query, style=SessionPreview.MATCH_STYLE
            )
        )
        if i < len(truncated) - 1:
            out.append("\n")
    if len(lines) > max_lines:
        out.append("\n…", style="dim")
    return out


def _indented_text(text: str, query: str, max_lines: int) -> Text:
    """Indent each line by two spaces; truncate to max_lines."""
    out = Text()
    lines = text.split("\n")
    truncated = lines[:max_lines]
    for i, line in enumerate(truncated):
        out.append("  ")
        out.append_text(
            highlight_matches(
                escape_markup(line), query, style=SessionPreview.MATCH_STYLE
            )
        )
        if i < len(truncated) - 1:
            out.append("\n")
    if len(lines) > max_lines:
        out.append("\n  …", style="dim")
    return out


# ----------------------------------------------------------------------------
# metrics
# ----------------------------------------------------------------------------


@dataclass
class _Metrics:
    user_turns: int
    assistant_turns: int
    code_blocks: int
    total_chars: int


def _compute_metrics(session: Session) -> _Metrics:
    """Cheap counts derived from the already-loaded `session.content`.

    No re-parsing of the JSONL — we just count the message-block markers the
    adapters emit. session.message_count is human turns including tool-only
    user messages, so we recompute user/assistant breakdown from content.
    """
    content = session.content or ""
    user_turns = 0
    assistant_turns = 0
    if content:
        for chunk in content.split("\n\n"):
            if chunk.startswith("» "):
                user_turns += 1
            elif chunk.startswith("  "):
                assistant_turns += 1
    code_blocks = len(SessionPreview.CODE_BLOCK_PATTERN.findall(content)) // 2
    return _Metrics(
        user_turns=user_turns,
        assistant_turns=assistant_turns,
        code_blocks=max(0, code_blocks),
        total_chars=len(content),
    )


# Kept for backwards compatibility with any external imports (e.g. tests that
# constructed a SessionPreview and called private helpers).
_RENDER_CODE_AVAILABLE = True


def _render_code(out: Text, code: str, language: str) -> None:
    """Pretty-print a code block via rich.Syntax. Currently unused by the
    structured preview but exposed for callers that want it."""
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
