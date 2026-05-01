"""Filter bar — All / Running / Recent view modes + per-agent filter buttons."""

from __future__ import annotations

from textual.containers import Horizontal
from textual.events import Click
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Label

from ..config import AGENTS

# Agent filter keys (None = "All agents")
AGENT_FILTER_KEYS: list[str | None] = [None, "claude", "codex"]

# View mode keys
VIEW_MODES: list[str] = ["all", "running", "recent"]


class FilterBar(Horizontal):
    """View mode buttons (All / Running / Recent) + agent filter pills."""

    class AgentChanged(Message):
        def __init__(self, filter_key: str | None) -> None:
            self.filter_key = filter_key
            super().__init__()

    class ViewChanged(Message):
        def __init__(self, view: str) -> None:
            self.view = view
            super().__init__()

    class ClaudeMemToggled(Message):
        """Posted when the user clicks the claude-mem chip."""

    active_agent: reactive[str | None] = reactive(None)
    active_view: reactive[str] = reactive("all")
    show_claude_mem: reactive[bool] = reactive(False)

    def __init__(
        self,
        initial_filter: str | None = None,
        initial_view: str = "all",
        initial_show_claude_mem: bool = False,
        id: str | None = None,
    ) -> None:
        super().__init__(id=id)
        self._initial_filter = initial_filter
        self._initial_view = initial_view
        self._initial_show_claude_mem = initial_show_claude_mem
        self._view_buttons: dict[str, Horizontal] = {}
        self._agent_buttons: dict[str | None, Horizontal] = {}
        self._mem_button: Horizontal | None = None

    def compose(self):
        # View modes
        for view in VIEW_MODES:
            label = view.capitalize()
            btn_id = f"filter-{view}"
            with Horizontal(id=btn_id, classes="filter-btn") as btn:
                yield Label(label, classes="filter-label")
            self._view_buttons[view] = btn

        yield Label("│", classes="filter-divider")

        # Agent filters
        for key in AGENT_FILTER_KEYS:
            label = AGENTS[key]["badge"] if key else "All agents"
            btn_id = f"filter-{key or 'all-agents'}"
            with Horizontal(id=btn_id, classes="filter-btn") as btn:
                yield Label(label, classes=f"filter-label agent-{key}" if key else "filter-label")
            self._agent_buttons[key] = btn

        yield Label("│", classes="filter-divider")

        # claude-mem visibility toggle. Active = mem sessions are visible.
        with Horizontal(id="filter-mem", classes="filter-btn") as mem_btn:
            yield Label("mem", classes="filter-label")
        self._mem_button = mem_btn

    def on_mount(self) -> None:
        self.active_agent = self._initial_filter
        self.active_view = self._initial_view
        self.show_claude_mem = self._initial_show_claude_mem
        self._update_styles()

    def watch_active_agent(self, _value: str | None) -> None:
        self._update_styles()

    def watch_active_view(self, _value: str) -> None:
        self._update_styles()

    def watch_show_claude_mem(self, _value: bool) -> None:
        self._update_styles()

    def _update_styles(self) -> None:
        for view, btn in self._view_buttons.items():
            if view == self.active_view:
                btn.add_class("-active")
            else:
                btn.remove_class("-active")
        for key, btn in self._agent_buttons.items():
            if key == self.active_agent:
                btn.add_class("-active")
            else:
                btn.remove_class("-active")
        if self._mem_button is not None:
            if self.show_claude_mem:
                self._mem_button.add_class("-active")
            else:
                self._mem_button.remove_class("-active")

    def set_active_agent(self, key: str | None, notify: bool = False) -> None:
        if key != self.active_agent:
            self.active_agent = key
            if notify:
                self.post_message(self.AgentChanged(key))

    def set_active_view(self, view: str, notify: bool = False) -> None:
        if view != self.active_view:
            self.active_view = view
            if notify:
                self.post_message(self.ViewChanged(view))

    def set_show_claude_mem(self, value: bool) -> None:
        self.show_claude_mem = value

    def on_click(self, event: Click) -> None:
        widget = event.widget
        while widget and widget is not self:
            wid = getattr(widget, "id", None)
            if wid and getattr(widget, "classes", None) and "filter-btn" in widget.classes:
                if wid.startswith("filter-"):
                    target = wid.removeprefix("filter-")
                    if target in VIEW_MODES:
                        self.set_active_view(target, notify=True)
                        return
                    if target == "all-agents":
                        self.set_active_agent(None, notify=True)
                        return
                    if target in {"claude", "codex"}:
                        self.set_active_agent(target, notify=True)
                        return
                    if target == "mem":
                        self.post_message(self.ClaudeMemToggled())
                        return
                return
            widget = widget.parent

    def update_agents_with_sessions(self, agents: set[str]) -> None:
        for key, btn in self._agent_buttons.items():
            if key is None or key in agents:
                btn.display = True
            else:
                btn.display = False
