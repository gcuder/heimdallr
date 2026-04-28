"""Results table widget — agent / title / directory / turns / date."""

from __future__ import annotations

from datetime import datetime

from rich.text import Text
from textual.message import Message
from textual.widgets import DataTable

from ..models import RunningInfo, Session
from .utils import (
    format_directory,
    format_time_ago,
    get_age_color,
    get_agent_icon,
    highlight_matches,
)

# (min_width, agent, dir, msgs, date)
_COL_WIDTHS = [
    (120, 13, 30, 6, 18),
    (90, 13, 22, 5, 15),
    (60, 13, 16, 5, 12),
    (0, 12, 0, 4, 10),
]


class ResultsTable(DataTable):
    """Session list with responsive columns and a running-status dot."""

    class Selected(Message):
        def __init__(self, session: Session | None) -> None:
            self.session = session
            super().__init__()

    def __init__(self, id: str | None = None) -> None:
        super().__init__(
            id=id,
            cursor_type="row",
            cursor_background_priority="renderable",
            cursor_foreground_priority="renderable",
        )
        self._displayed_sessions: list[Session] = []
        self._title_width: int = 60
        self._dir_width: int = 22
        self._current_query: str = ""
        self._running_state: dict[str, RunningInfo] = {}
        self._pinned_ids: set[str] = set()

    def on_mount(self) -> None:
        (
            self._col_agent,
            self._col_title,
            self._col_dir,
            self._col_msgs,
            self._col_date,
        ) = self.add_columns("Agent", "Title", "Directory", "Turns", "Date")
        self._update_responsive_widths()

    def on_resize(self) -> None:
        if hasattr(self, "_col_agent"):
            self._update_responsive_widths()
            if self._displayed_sessions:
                self._render_sessions()

    def _update_responsive_widths(self) -> None:
        width = self.size.width or 120
        agent_w, dir_w, msgs_w, date_w = next(
            (a, d, m, t) for min_w, a, d, m, t in _COL_WIDTHS if width >= min_w
        )
        title_w = max(15, width - agent_w - dir_w - msgs_w - date_w - 8)
        for col in self.columns.values():
            col.auto_width = False
        self.columns[self._col_agent].width = agent_w
        self.columns[self._col_title].width = title_w
        self.columns[self._col_dir].width = dir_w
        self.columns[self._col_msgs].width = msgs_w
        self.columns[self._col_date].width = date_w
        self._title_width, self._dir_width = title_w, dir_w
        self.refresh()

    def update_sessions(
        self, sessions: list[Session], query: str = ""
    ) -> Session | None:
        self._displayed_sessions = sessions
        self._current_query = query
        self._render_sessions()
        if sessions:
            self.move_cursor(row=0)
            return sessions[0]
        return None

    def update_running_state(self, running: dict[str, RunningInfo]) -> None:
        """Update only the running indicators without re-rendering everything."""
        if running == self._running_state:
            return
        self._running_state = running
        if self._displayed_sessions:
            self._render_sessions()

    def update_pinned_state(self, pinned: set[str]) -> None:
        if pinned == self._pinned_ids:
            return
        self._pinned_ids = pinned
        if self._displayed_sessions:
            self._render_sessions()

    def _render_sessions(self) -> None:
        self.clear()
        if not self._displayed_sessions:
            self.add_row("", Text("No sessions found", style="dim italic"), "", "", "")
            return

        for session in self._displayed_sessions:
            info = self._running_state.get(session.id)
            running = info.is_running if info else False
            low_conf = (info.confidence == "low") if info else False
            icon = get_agent_icon(session.agent, running=running, low_confidence=low_conf)

            pin_prefix = "★ " if session.id in self._pinned_ids else ""
            title_text = highlight_matches(
                session.title,
                self._current_query,
                max_len=max(10, self._title_width - len(pin_prefix)),
            )
            if pin_prefix:
                title = Text("★ ", style="bold #facc15")
                title.append_text(title_text)
            else:
                title = title_text

            dir_w = self._dir_width
            directory = format_directory(session.directory)
            if dir_w > 0 and len(directory) > dir_w:
                directory = "..." + directory[-(dir_w - 3):]
            dir_text = (
                highlight_matches(directory, self._current_query) if dir_w > 0 else Text("")
            )

            msgs_text = str(session.message_count) if session.message_count > 0 else "-"

            time_ago = format_time_ago(session.timestamp)
            time_text = Text(time_ago.rjust(8))
            age_hours = (datetime.now() - session.timestamp).total_seconds() / 3600
            time_text.stylize(get_age_color(age_hours))

            self.add_row(icon, title, dir_text, msgs_text, time_text)

    def get_selected_session(self) -> Session | None:
        if self.cursor_row is not None and self.cursor_row < len(self._displayed_sessions):
            return self._displayed_sessions[self.cursor_row]
        return None

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self.post_message(self.Selected(self.get_selected_session()))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        from .app import HeimdallrApp

        assert isinstance(self.app, HeimdallrApp)
        if session := self.get_selected_session():
            self.app.selected_session = session
        self.app.action_resume_session()

    @property
    def displayed_sessions(self) -> list[Session]:
        return self._displayed_sessions
