"""Main TUI application."""

from __future__ import annotations

import logging
import os
import shlex
import time
from datetime import datetime, timedelta

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.widgets import Footer, Input, Label

from .. import __version__, bookmarks, settings
from ..config import DB_PATH, LOG_FILE
from ..models import ParseError, RunningInfo, Session
from ..running import (
    RunningDetector,
    RunningSnapshot,
    find_terminal_pid,
    spawn_new_terminal,
    wrapper_path,
)
from ..running.ide_activate import activate as activate_pid
from ..search import SessionSearch
from ..transfer import build_inject_plan, execute_plan
from .filter_bar import AGENT_FILTER_KEYS, VIEW_MODES, FilterBar
from .logo import LogoWidget
from .preview import SessionPreview
from .query import extract_agent_from_query, update_agent_in_query
from .results_table import ResultsTable
from .search_input import KeywordHighlighter, KeywordSuggester
from .styles import APP_CSS
from .transfer_modal import TransferModal, TransferResult
from .utils import copy_to_clipboard

logger = logging.getLogger(__name__)


class HeimdallrApp(App):
    """heimdallr — manage Claude Code and Codex sessions."""

    ENABLE_COMMAND_PALETTE = True
    TITLE = "heimdallr"
    SUB_TITLE = "Session manager"
    CSS = APP_CSS

    BINDINGS = [
        Binding("escape", "quit", "Quit", priority=True),
        Binding("q", "quit", "Quit", show=False),
        Binding("ctrl+c", "quit", "Quit", show=False),
        Binding("/", "focus_search", "Search", priority=True),
        Binding("enter", "resume_session", "Resume"),
        Binding("shift+enter", "resume_session_yolo", "YOLO"),
        Binding("c", "copy_path", "Copy", priority=True),
        Binding("ctrl+grave_accent", "toggle_preview", "Preview", priority=True),
        Binding("tab", "accept_suggestion", "Accept", show=False, priority=True),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("up", "cursor_up", "Up", show=False),
        Binding("pagedown", "page_down", "PgDn", show=False),
        Binding("pageup", "page_up", "PgUp", show=False),
        Binding("1", "view_mode('all')", "All"),
        Binding("2", "view_mode('running')", "Running"),
        Binding("3", "view_mode('recent')", "Recent"),
        Binding("r", "rescan", "Rescan", show=False),
        Binding("i", "activate_ide", "Jump to IDE", show=False),
        Binding("t", "transfer", "Transfer", show=False),
        Binding("p", "toggle_pin", "Pin", show=False),
        Binding("m", "toggle_claude_mem", "Mem", show=False),
        Binding("o", "cycle_sort", "Sort", show=False),
        Binding("s", "settings", "Settings"),
        Binding("question_mark", "help", "Help", show=False),
        Binding("ctrl+p", "command_palette", "Cmds"),
    ]

    show_preview: reactive[bool] = reactive(True)
    selected_session: reactive[Session | None] = reactive(None)
    active_filter: reactive[str | None] = reactive(None)
    active_view: reactive[str] = reactive("all")
    sort_mode: reactive[str] = reactive("recent")  # recent | running | pinned | project
    is_loading: reactive[bool] = reactive(True)
    search_query: reactive[str] = reactive("", init=False)
    query_time_ms: reactive[float | None] = reactive(None)
    _spinner_frame: int = 0
    _spinner_chars: str = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(
        self,
        initial_query: str = "",
        agent_filter: str | None = None,
        yolo: bool = False,
    ):
        super().__init__()
        s = settings.current()
        # Seed reactives + state from persisted settings before mount.
        self.theme = s.display.theme
        self.sort_mode = s.display.sort_mode
        self.show_preview = s.display.show_preview
        self.active_view = s.filters.default_view
        self.search_engine = SessionSearch()
        self.initial_query = initial_query
        self.agent_filter = agent_filter if agent_filter is not None else s.filters.default_agent
        self.yolo = yolo or s.resume.yolo_default
        self.sessions: list[Session] = []
        self._resume_command: list[str] | None = None
        self._resume_directory: str | None = None
        self._resume_session_id: str | None = None
        self._resume_agent: str | None = None
        self._current_query: str = ""
        self._total_loaded: int = 0
        self._search_timer = None
        self._syncing_filter: bool = False
        self._running_info: dict[str, RunningInfo] = {}
        self._detector: RunningDetector | None = None
        self._pinned: set[str] = set()

    # ---- composition ------------------------------------------------------

    def compose(self) -> ComposeResult:
        s = settings.current()
        with Vertical():
            with Horizontal(id="title-bar"):
                if s.display.show_logo:
                    yield LogoWidget()
                with Vertical(id="title-text"):
                    yield Label(f"heimdallr v{__version__}", id="app-title")
                    yield Label("", id="session-count")

            with Horizontal(id="search-row"):
                with Horizontal(id="search-box"):
                    yield Label("🔍", id="search-icon")
                    yield Input(
                        placeholder="Search titles & messages. Try agent:claude or date:today",
                        id="search-input",
                        value=self.initial_query,
                        highlighter=KeywordHighlighter(),
                        suggester=KeywordSuggester(),
                    )
                    yield Label("", id="query-time")

            yield FilterBar(
                initial_filter=self.agent_filter,
                initial_view=s.filters.default_view,
                initial_show_claude_mem=not s.filters.hide_claude_mem,
                id="filter-container",
            )

            with Vertical(id="main-container"):
                with Vertical(id="results-container"):
                    yield ResultsTable(id="results-table")
                with VerticalScroll(id="preview-container"):
                    yield SessionPreview()

            yield Label("", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        self.active_filter = self.agent_filter
        self._pinned = bookmarks.get_pinned_ids()
        self.query_one("#search-input", Input).focus()
        self._spinner_timer = self.set_interval(0.08, self._update_spinner)
        self._initial_load()
        self._start_detector()

    def on_unmount(self) -> None:
        if self._detector is not None:
            self._detector.stop()

    # ---- loading ---------------------------------------------------------

    def _initial_load(self) -> None:
        sessions = self.search_engine._load_from_index()
        table = self.query_one(ResultsTable)
        table.update_pinned_state(self._pinned)
        if sessions is not None:
            self.search_engine._sessions = sessions
            self._total_loaded = len(sessions)
            t0 = time.perf_counter()
            self.sessions = self.search_engine.search(
                self.initial_query, agent_filter=self.active_filter, limit=100
            )
            self.query_time_ms = (time.perf_counter() - t0) * 1000
            self._finish_loading()
            self.selected_session = table.update_sessions(
                self._apply_view_filter(self.sessions), self._current_query
            )
        else:
            table.update_sessions([], self._current_query)
            self._update_session_count()
            self._do_streaming_load()

    def _update_spinner(self) -> None:
        icon = self.query_one("#search-icon", Label)
        if self.is_loading:
            self._spinner_frame = (self._spinner_frame + 1) % len(self._spinner_chars)
            icon.update(self._spinner_chars[self._spinner_frame])
        else:
            icon.update("🔍")

    def _update_session_count(self) -> None:
        count_label = self.query_one("#session-count", Label)
        time_label = self.query_one("#query-time", Label)
        if self.is_loading:
            count_label.update(f"{self._total_loaded} sessions loaded")
            time_label.update("")
            return
        shown = len(self._displayed_sessions)
        total = self.search_engine.get_session_count(self.active_filter)
        running_n = sum(1 for info in self._running_info.values() if info.is_running)
        prefix = f"{shown}/{total}" if shown < total else f"{total}"
        running_part = f" · ● {running_n} running" if running_n else ""
        count_label.update(f"{prefix} sessions{running_part}")
        time_label.update(f"{self.query_time_ms:.1f}ms" if self.query_time_ms is not None else "")

    @work(exclusive=True, thread=True)
    def _do_streaming_load(self) -> None:
        parse_errors: list[ParseError] = []

        def on_progress() -> None:
            t0 = time.perf_counter()
            sessions = self.search_engine.search(
                self.initial_query, agent_filter=self.active_filter, limit=100
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000
            total = self.search_engine.get_session_count()
            self.call_from_thread(self._update_results_streaming, sessions, total, elapsed_ms)

        def on_error(error: ParseError) -> None:
            parse_errors.append(error)

        _, new, updated, deleted = self.search_engine.index_sessions_parallel(
            on_progress, on_error=on_error
        )
        on_progress()
        self.call_from_thread(self._finish_loading, new, updated, deleted, len(parse_errors))

    def _update_results_streaming(
        self, sessions: list[Session], total: int, elapsed_ms: float | None = None
    ) -> None:
        self.sessions = sessions
        self._total_loaded = total
        if elapsed_ms is not None:
            self.query_time_ms = elapsed_ms
        try:
            table = self.query_one(ResultsTable)
        except NoMatches:
            return
        self.selected_session = table.update_sessions(
            self._apply_view_filter(sessions), self._current_query
        )
        self._update_session_count()

    def _finish_loading(
        self, new: int = 0, updated: int = 0, deleted: int = 0, errors: int = 0
    ) -> None:
        self.is_loading = False
        if hasattr(self, "_spinner_timer"):
            self._spinner_timer.stop()
        self._update_spinner()
        self._update_session_count()

        agents = self.search_engine.get_agents_with_sessions()
        self.query_one(FilterBar).update_agents_with_sessions(agents)

        if new or updated or deleted:
            parts = []
            if new:
                parts.append(f"{new} new session{'s' if new != 1 else ''}")
            if updated:
                parts.append(f"{updated} updated" if parts else f"{updated} session{'s' if updated != 1 else ''} updated")
            if deleted:
                parts.append(f"{deleted} deleted" if parts else f"{deleted} session{'s' if deleted != 1 else ''} deleted")
            self.notify(", ".join(parts), title="Index updated")

        if errors:
            home = os.path.expanduser("~")
            log_path = str(LOG_FILE)
            if log_path.startswith(home):
                log_path = "~" + log_path[len(home):]
            self.notify(
                f"{errors} session{'s' if errors != 1 else ''} failed to parse. See {log_path}",
                severity="warning",
                timeout=5,
            )

    # ---- search -----------------------------------------------------------

    @work(exclusive=True, thread=True)
    def _do_search(self, query: str) -> None:
        self._current_query = query
        t0 = time.perf_counter()
        sessions = self.search_engine.search(
            query, agent_filter=self.active_filter, limit=100
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        self.call_from_thread(self._update_results, sessions, elapsed_ms)

    def _update_results(self, sessions: list[Session], elapsed_ms: float | None = None) -> None:
        self.sessions = sessions
        if elapsed_ms is not None:
            self.query_time_ms = elapsed_ms
        if not self.search_engine._streaming_in_progress:
            self.is_loading = False
        try:
            table = self.query_one(ResultsTable)
        except NoMatches:
            return
        self.selected_session = table.update_sessions(
            self._apply_view_filter(sessions), self._current_query
        )
        self._update_session_count()

    def _apply_view_filter(self, sessions: list[Session]) -> list[Session]:
        if self.active_view == "running":
            filtered = [
                s for s in sessions if (info := self._running_info.get(s.id)) and info.is_running
            ]
        elif self.active_view == "recent":
            cutoff = datetime.now() - timedelta(hours=24)
            filtered = [s for s in sessions if s.timestamp >= cutoff]
        else:
            filtered = list(sessions)
        return self._apply_sort(filtered)

    def _apply_sort(self, sessions: list[Session]) -> list[Session]:
        mode = self.sort_mode
        if mode == "running":
            return sorted(
                sessions,
                key=lambda s: (
                    not (
                        (info := self._running_info.get(s.id)) is not None and info.is_running
                    ),
                    -s.timestamp.timestamp(),
                ),
            )
        if mode == "pinned":
            return sorted(
                sessions,
                key=lambda s: (s.id not in self._pinned, -s.timestamp.timestamp()),
            )
        if mode == "project":
            return sorted(
                sessions,
                key=lambda s: (s.directory or "", -s.timestamp.timestamp()),
            )
        # recent (default)
        return sessions

    # ---- running detector ------------------------------------------------

    def _start_detector(self) -> None:
        if self._detector is not None:
            return
        self._detector = RunningDetector(
            adapters=self.search_engine.adapters,
            get_sessions=lambda: list(self.search_engine._sessions_by_id.values()),
        )
        self._detector.start(post=self.post_message)

    @on(RunningSnapshot)
    def on_running_snapshot(self, event: RunningSnapshot) -> None:
        self._running_info = event.info
        try:
            table = self.query_one(ResultsTable)
        except NoMatches:
            return
        table.update_running_state(event.info)
        # Re-apply view filter when a session enters/leaves running state.
        if self.active_view == "running":
            self.selected_session = table.update_sessions(
                self._apply_view_filter(self.sessions), self._current_query
            )
        # Refresh detail pane if the highlighted session's state changed.
        if self.selected_session is not None:
            preview = self.query_one(SessionPreview)
            preview.update_preview(
                self.selected_session,
                self._current_query,
                running_info=self._running_info.get(self.selected_session.id),
            )
        self._update_session_count()

    @on(ResultsTable.Selected)
    def on_results_table_selected(self, event: ResultsTable.Selected) -> None:
        if event.session:
            self.selected_session = event.session
            preview = self.query_one(SessionPreview)
            preview.update_preview(
                event.session,
                self._current_query,
                running_info=self._running_info.get(event.session.id),
            )

    @on(Input.Changed, "#search-input")
    def on_search_changed(self, event: Input.Changed) -> None:
        if self._search_timer:
            self._search_timer.stop()
        self.is_loading = True

        if not self._syncing_filter:
            agent_in_query = extract_agent_from_query(event.value)
            if agent_in_query != self.active_filter:
                if agent_in_query is None or agent_in_query in AGENT_FILTER_KEYS:
                    self._syncing_filter = True
                    self.active_filter = agent_in_query
                    self.query_one(FilterBar).set_active_agent(agent_in_query)
                    self._syncing_filter = False

        value = event.value
        self._search_timer = self.set_timer(
            0.05, lambda: setattr(self, "search_query", value)
        )

    def watch_search_query(self, query: str) -> None:
        self._do_search(query)

    @on(Input.Submitted, "#search-input")
    def on_search_submitted(self, event: Input.Submitted) -> None:
        self.action_resume_session()

    # ---- resume -----------------------------------------------------------

    def action_copy_path(self) -> None:
        """Copy resume command to clipboard. Plain `c` copies normal-mode."""
        if not self.selected_session:
            return
        self._do_copy_command(yolo=self.yolo or self.selected_session.yolo)

    def _do_copy_command(self, yolo: bool) -> None:
        assert self.selected_session is not None
        cmd = self.search_engine.get_resume_command(self.selected_session, yolo=yolo)
        if not cmd:
            self.notify("No resume command available", severity="warning", timeout=2)
            return
        directory = self.selected_session.directory
        cmd_str = shlex.join(cmd)
        full = f"cd {shlex.quote(directory)} && {cmd_str}" if directory else cmd_str
        if copy_to_clipboard(full):
            self.notify(f"Copied: {full}", timeout=3)
        else:
            self.notify(full, title="Clipboard unavailable", timeout=5)

    def action_resume_session(self) -> None:
        """Resume the selected session. Jump to a running terminal if one
        exists; otherwise spawn a new terminal window via the CLI."""
        if not self.selected_session:
            return
        self._do_resume(yolo=self.yolo or self.selected_session.yolo)

    def action_resume_session_yolo(self) -> None:
        """Resume with `--dangerously-skip-permissions` (Claude) regardless
        of the user's normal default."""
        if not self.selected_session:
            return
        self._do_resume(yolo=True)

    def _do_resume(self, yolo: bool) -> None:
        assert self.selected_session is not None
        sess = self.selected_session
        running = self._running_info.get(sess.id)

        # If the session is already running, never spawn a duplicate. Try to
        # jump to whichever window hosts it; if we can't locate a window,
        # keep hmd open and notify rather than silently relaunching.
        if running and running.is_running:
            if self._jump_to_running_window(running):
                return
            self.notify(
                "Session is running but I couldn't locate its terminal/IDE window.",
                severity="warning",
                timeout=5,
            )
            return

        # Not running — spawn a new terminal window directly so hmd stays
        # open. Only exit and let the CLI take over if window-spawning isn't
        # available (Linux, no $TERM_PROGRAM, etc.).
        cmd = self.search_engine.get_resume_command(sess, yolo=yolo)
        if not cmd:
            self.notify("No resume command available", severity="warning", timeout=3)
            return
        directory = sess.directory or os.getcwd()
        argv = self._build_wrapped_argv(sess.id, sess.agent, cmd)

        bookmarks.record_open(sess.id)

        if spawn_new_terminal(directory, argv, app=settings.current().resume.terminal):
            self.notify(
                f"Resumed in new terminal — {sess.title[:40]}", timeout=3
            )
            return

        # Fallback: hand off to the CLI which will os.execvp in this shell.
        self._resume_command = cmd
        self._resume_directory = directory
        self._resume_session_id = sess.id
        self._resume_agent = sess.agent
        self.exit()

    def _build_wrapped_argv(
        self, session_id: str, agent: str, cmd: list[str]
    ) -> list[str]:
        """Wrap the agent invocation through resume_wrapper.sh so its $$
        lands in spawned_pids — gives the detector high-confidence ownership."""
        return [
            "/bin/sh",
            str(wrapper_path()),
            str(DB_PATH),
            session_id,
            agent,
            *cmd,
        ]

    def _jump_to_running_window(self, running: RunningInfo) -> bool:
        """Bring the window hosting `running` to the front. Order is driven
        by `resume.prefer_ide`: terminal-first by default, IDE-first when
        the user has the editor as their main work surface."""
        prefer_ide = settings.current().resume.prefer_ide
        order = ("ide", "terminal") if prefer_ide else ("terminal", "ide")
        for kind in order:
            if kind == "terminal" and running.pid:
                term = find_terminal_pid(running.pid)
                if term is not None:
                    ok, msg = activate_pid(term.pid, term.name)
                    if ok:
                        self.notify(f"Jumped to {term.name}", timeout=3)
                        return True
                    logger.debug("activate_pid(terminal=%s) failed: %s", term.name, msg)
                else:
                    logger.debug("find_terminal_pid(pid=%s) returned no match", running.pid)
            elif kind == "ide" and running.ide_pid:
                ok, msg = activate_pid(running.ide_pid, running.ide)
                if ok:
                    self.notify(f"Jumped to {running.ide}", timeout=3)
                    return True
                logger.debug("activate_pid(ide=%s) failed: %s", running.ide, msg)
        return False

    # ---- ui actions -------------------------------------------------------

    def action_focus_search(self) -> None:
        self.query_one("#search-input", Input).focus()

    def action_toggle_preview(self) -> None:
        self.show_preview = not self.show_preview
        c = self.query_one("#preview-container")
        if self.show_preview:
            c.remove_class("hidden")
        else:
            c.add_class("hidden")

    def action_cursor_down(self) -> None:
        self.query_one(ResultsTable).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one(ResultsTable).action_cursor_up()

    def action_page_down(self) -> None:
        table = self.query_one(ResultsTable)
        for _ in range(10):
            table.action_cursor_down()

    def action_page_up(self) -> None:
        table = self.query_one(ResultsTable)
        for _ in range(10):
            table.action_cursor_up()

    def action_view_mode(self, mode: str) -> None:
        if mode not in VIEW_MODES:
            return
        self.active_view = mode
        self.query_one(FilterBar).set_active_view(mode)
        try:
            table = self.query_one(ResultsTable)
        except NoMatches:
            return
        self.selected_session = table.update_sessions(
            self._apply_view_filter(self.sessions), self._current_query
        )
        self._update_session_count()

    def action_toggle_pin(self) -> None:
        if not self.selected_session:
            return
        new_state = bookmarks.toggle_pin(self.selected_session.id)
        if new_state:
            self._pinned.add(self.selected_session.id)
            self.notify(f"Pinned: {self.selected_session.title[:40]}", timeout=2)
        else:
            self._pinned.discard(self.selected_session.id)
            self.notify(f"Unpinned: {self.selected_session.title[:40]}", timeout=2)
        try:
            table = self.query_one(ResultsTable)
        except NoMatches:
            return
        table.update_pinned_state(self._pinned)
        if self.sort_mode == "pinned":
            self.selected_session = table.update_sessions(
                self._apply_view_filter(self.sessions), self._current_query
            )

    _SORT_MODES = ["recent", "running", "pinned", "project"]

    def action_cycle_sort(self) -> None:
        idx = self._SORT_MODES.index(self.sort_mode)
        self.sort_mode = self._SORT_MODES[(idx + 1) % len(self._SORT_MODES)]
        self.notify(f"Sort: {self.sort_mode}", timeout=2)
        try:
            table = self.query_one(ResultsTable)
        except NoMatches:
            return
        self.selected_session = table.update_sessions(
            self._apply_view_filter(self.sessions), self._current_query
        )

    def action_help(self) -> None:
        from .help_modal import HelpModal

        self.push_screen(HelpModal())

    def action_settings(self) -> None:
        from .settings_modal import SettingsModal

        self.push_screen(SettingsModal())

    def action_transfer(self) -> None:
        """Open the transfer modal for the selected session."""
        if not self.selected_session:
            self.notify("No session selected", severity="warning", timeout=2)
            return
        self.push_screen(
            TransferModal(self.selected_session),
            self._on_transfer_result,
        )

    def _on_transfer_result(self, result: TransferResult | None) -> None:
        if result is None:
            return
        assert self.selected_session is not None
        cwd = self.selected_session.directory or os.getcwd()
        try:
            plan = build_inject_plan(
                bundle=result.bundle,
                target_agent=result.target_agent,
                target_session_id=None,  # always-new-session for v1
                cwd=cwd,
            )
        except ValueError as e:
            self.notify(str(e), severity="error", timeout=4)
            return
        try:
            execute_plan(plan)
        except Exception as e:
            self.notify(f"Transfer failed: {e}", severity="error", timeout=5)
            return
        # Stage as a "resume command" — cli.py will exec via the wrapper so
        # the new session is also self-PID-tracked.
        self._resume_command = plan.argv
        self._resume_directory = plan.cwd
        # Use a synthetic session id so spawned_pids row is meaningful even
        # for the brand-new target session whose real id we don't know yet.
        self._resume_session_id = f"transfer:{plan.bundle.source_session_id}"
        self._resume_agent = plan.target_agent
        self.exit()

    def action_activate_ide(self) -> None:
        """Bring the IDE window attached to the selected session to the front."""
        from ..running.ide_activate import activate

        if not self.selected_session:
            return
        info = self._running_info.get(self.selected_session.id)
        if info is None or info.ide is None or info.ide_pid is None:
            self.notify("No IDE attached to this session", severity="warning", timeout=3)
            return
        ok, msg = activate(info.ide_pid, info.ide)
        self.notify(msg, severity="information" if ok else "warning", timeout=3)

    def action_rescan(self) -> None:
        self.is_loading = True
        if hasattr(self, "_spinner_timer"):
            self._spinner_timer = self.set_interval(0.08, self._update_spinner)
        self.search_engine._sessions = None
        self._do_streaming_load()

    def _set_filter(self, agent: str | None) -> None:
        self.active_filter = agent
        self.query_one(FilterBar).set_active_agent(agent)

        if not self._syncing_filter:
            self._syncing_filter = True
            search_input = self.query_one("#search-input", Input)
            new_query = update_agent_in_query(search_input.value, agent)
            if new_query != search_input.value:
                search_input.value = new_query
                self._current_query = new_query
            self._syncing_filter = False

        self._do_search(self._current_query)

    def action_accept_suggestion(self) -> None:
        search_input = self.query_one("#search-input", Input)
        if search_input._suggestion:
            search_input.action_cursor_right()

    async def action_quit(self) -> None:
        from textual.screen import ModalScreen

        if len(self.screen_stack) > 1:
            top = self.screen_stack[-1]
            if isinstance(top, ModalScreen):
                top.dismiss(None)
            return
        # First escape: defocus the search input so digit/letter shortcuts
        # work. Second escape (or any other unfocused-quit trigger) actually
        # quits.
        search_input = self.query_one("#search-input", Input)
        if search_input.has_focus:
            self.query_one(ResultsTable).focus()
            return
        self.exit()

    @on(FilterBar.AgentChanged)
    def on_filter_bar_agent_changed(self, event: FilterBar.AgentChanged) -> None:
        self._set_filter(event.filter_key)

    @on(FilterBar.ViewChanged)
    def on_filter_bar_view_changed(self, event: FilterBar.ViewChanged) -> None:
        self.action_view_mode(event.view)

    @on(FilterBar.ClaudeMemToggled)
    def on_filter_bar_claude_mem_toggled(
        self, _event: FilterBar.ClaudeMemToggled
    ) -> None:
        self.action_toggle_claude_mem()

    def action_toggle_claude_mem(self) -> None:
        s = settings.current()
        s.filters.hide_claude_mem = not s.filters.hide_claude_mem
        settings.update(s)
        self.query_one(FilterBar).set_show_claude_mem(not s.filters.hide_claude_mem)
        self.notify(
            "Showing claude-mem sessions"
            if not s.filters.hide_claude_mem
            else "Hiding claude-mem sessions",
            timeout=2,
        )
        self._do_search(self._current_query)

    # ---- settings live-apply ---------------------------------------------

    def on_setting_changed(self, event) -> None:  # type: ignore[no-untyped-def]
        """Live-apply settings as they're toggled in the SettingsModal."""
        from .settings_modal import SettingChanged

        if not isinstance(event, SettingChanged):
            return
        s = settings.current()

        if event.section == "display":
            if event.field in ("theme", "*"):
                self.theme = s.display.theme
            if event.field in ("show_logo", "*"):
                try:
                    self.query_one(LogoWidget).display = s.display.show_logo
                except Exception:
                    # Logo wasn't composed (started with show_logo=False) —
                    # toggle takes effect on next launch.
                    pass
            if event.field in ("sort_mode", "*"):
                self.sort_mode = s.display.sort_mode
                self._refresh_table()
            if event.field in ("show_preview", "*"):
                self.show_preview = s.display.show_preview
                self._apply_preview_visibility()

        elif event.section == "filters":
            if event.field in ("hide_claude_mem", "*"):
                try:
                    self.query_one(FilterBar).set_show_claude_mem(
                        not s.filters.hide_claude_mem
                    )
                except Exception:
                    pass
            if event.field in ("default_agent", "*"):
                self._set_filter(s.filters.default_agent)
                return  # _set_filter triggers a search on its own
            if event.field in ("default_view", "*"):
                self.action_view_mode(s.filters.default_view)
                return
            self._do_search(self._current_query)

        elif event.section in ("resume", "transfer"):
            # No live UI effect — picked up at next resume / transfer.
            pass

        elif event.section == "notifications":
            # Picked up via settings.current() at notify-time. No action.
            pass

        elif event.section == "keybindings":
            # Effective on next launch — Textual rebinding mid-session is
            # not safely supported. Notification was already shown by the
            # capture handler.
            pass

    def _refresh_table(self) -> None:
        try:
            table = self.query_one(ResultsTable)
        except NoMatches:
            return
        self.selected_session = table.update_sessions(
            self._apply_view_filter(self.sessions), self._current_query
        )

    def _apply_preview_visibility(self) -> None:
        try:
            container = self.query_one("#preview-container")
        except NoMatches:
            return
        if self.show_preview:
            container.remove_class("hidden")
        else:
            container.add_class("hidden")

    # ---- exit-time handoff to CLI ----------------------------------------

    def get_resume_command(self) -> list[str] | None:
        return self._resume_command

    def get_resume_directory(self) -> str | None:
        return self._resume_directory

    def get_resume_session_id(self) -> str | None:
        return self._resume_session_id

    def get_resume_agent(self) -> str | None:
        return self._resume_agent

    @property
    def _displayed_sessions(self) -> list[Session]:
        try:
            return self.query_one(ResultsTable).displayed_sessions
        except Exception:
            return []
