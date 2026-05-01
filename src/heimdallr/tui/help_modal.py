"""Help overlay listing every keybinding, grouped by category."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Label

from .styles import HELP_MODAL_CSS

# Keep this list aligned with HeimdallrApp.BINDINGS — single source of UX truth.
_HELP: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "Navigation",
        [
            ("↑ ↓ / j k", "Move cursor up / down"),
            ("PgUp PgDn", "Page up / down (~10 rows)"),
            ("/", "Focus the search box"),
            ("escape", "Defocus search (then quit on second press)"),
            ("q   ctrl+c", "Quit"),
            ("tab", "Accept search autocomplete suggestion"),
        ],
    ),
    (
        "Actions",
        [
            ("enter", "Resume — jump to running terminal or spawn a new window"),
            ("shift+enter", "Resume in YOLO mode (Claude --dangerously-skip-permissions)"),
            ("c", "Copy resume command to clipboard"),
            ("t", "Open transfer modal (compact + inject context)"),
            ("p", "Pin / unpin the highlighted session"),
            ("m", "Toggle visibility of claude-mem observer sessions"),
            ("i", "Bring the attached IDE window to the front"),
            ("r", "Force a full rescan + reindex"),
        ],
    ),
    (
        "Views & sort",
        [
            ("1   2   3", "View: All / Running / Recent (last 24h)"),
            ("o", "Cycle sort: recent → running → pinned → project"),
            ("ctrl+`", "Toggle preview pane"),
        ],
    ),
    (
        "Search syntax",
        [
            ("agent:claude", "Filter to one agent (also: codex). Comma for OR."),
            ("-agent:codex", "Exclude an agent."),
            ("dir:project", "Substring match on session directory."),
            ("date:today", "Today, yesterday, week, month, <1h, >2d, etc."),
        ],
    ),
]


class HelpModal(ModalScreen[None]):
    BINDINGS = [
        Binding("escape", "dismiss_screen", "Close", show=False),
        Binding("question_mark", "dismiss_screen", "Close", show=False),
        Binding("q", "dismiss_screen", "Close", show=False),
    ]
    CSS = HELP_MODAL_CSS

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("heimdallr — keybindings", id="title")
            with VerticalScroll():
                for section, rows in _HELP:
                    yield Label(section, classes="help-section")
                    for key, desc in rows:
                        with Horizontal(classes="help-row"):
                            yield Label(key, classes="help-key")
                            yield Label(desc, classes="help-desc")
            yield Label("Press ? or escape to close", id="footer")

    def action_dismiss_screen(self) -> None:
        self.dismiss(None)
