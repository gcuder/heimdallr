"""In-TUI settings screen — live-apply, persistent across launches.

Layout: ~80% wide x 80% tall centred modal.
  ┌─ Settings ─────────────────────────────────┐
  │ ┌── nav ────┐  ┌── pane ──────────────────┐│
  │ │ Display █ │  │ controls for the         ││
  │ │ Filters   │  │ active section           ││
  │ │ ...       │  │                          ││
  │ └───────────┘  └──────────────────────────┘│
  │ tab section · esc close · ? help            │
  └─────────────────────────────────────────────┘

Every change is persisted immediately (no Save button) and broadcast as a
`SettingChanged` message — `HeimdallrApp` listens and applies the live
effect (theme repaint, list refresh, etc.).
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Input,
    Label,
    ListItem,
    ListView,
    Select,
    Static,
    Switch,
    TextArea,
)

from .. import __version__, settings
from ..config import DB_PATH, INDEX_DIR, LOG_FILE
from .styles import SETTINGS_MODAL_CSS

# ---------------------------------------------------------------------------
# Section metadata
# ---------------------------------------------------------------------------

SECTIONS: list[tuple[str, str]] = [
    ("display", "Display"),
    ("filters", "Filters"),
    ("sessions", "Sessions"),
    ("resume", "Resume"),
    ("transfer", "Transfer"),
    ("notifications", "Notifications"),
    ("keybindings", "Keybindings"),
    ("diagnostics", "Diagnostics"),
]

_AGENT_OPTIONS: list[tuple[str, str]] = [
    ("All agents", "all"),
    ("claude", "claude"),
    ("codex", "codex"),
]

_VIEW_OPTIONS: list[tuple[str, str]] = [
    ("All", "all"),
    ("Running", "running"),
    ("Recent (24h)", "recent"),
]

_SORT_OPTIONS: list[tuple[str, str]] = [
    ("Recent", "recent"),
    ("Running first", "running"),
    ("Pinned first", "pinned"),
    ("By project", "project"),
]


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


@dataclass
class SettingChanged(Message):
    """Posted after a setting is mutated and persisted. App reacts live."""

    section: str
    field: str
    value: object


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _open_in_finder(path: str) -> None:
    """Best-effort 'reveal in file manager'. macOS: `open -R`. Linux: xdg-open."""
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(path) or "."])
    except OSError:
        pass


def _agent_to_choice(value: str | None) -> str:
    return value or "all"


def _choice_to_agent(value: str) -> str | None:
    return None if value == "all" else value


# ---------------------------------------------------------------------------
# Modal
# ---------------------------------------------------------------------------


class SettingsModal(ModalScreen[None]):
    """Settings screen — section nav on the left, controls on the right."""

    BINDINGS = [
        Binding("escape", "dismiss_screen", "Close", show=False),
        Binding("q", "dismiss_screen", "Close", show=False),
    ]
    CSS = SETTINGS_MODAL_CSS

    current_section: reactive[str] = reactive("display")

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-root"):
            yield Label("Settings", id="settings-title")
            with Horizontal(id="settings-body"):
                with Vertical(id="settings-nav"):
                    yield ListView(
                        *[
                            ListItem(Label(label), id=f"nav-{key}")
                            for key, label in SECTIONS
                        ],
                        id="section-list",
                    )
                with VerticalScroll(id="settings-pane"):
                    for key, _ in SECTIONS:
                        yield Vertical(id=f"section-{key}", classes="section-panel")
            yield Label(
                "Tab/↓↑ section  ·  Enter edit  ·  Esc close",
                id="settings-hint",
            )

    def on_mount(self) -> None:
        self._build_section_panels()
        self._show_section(self.current_section)
        self.query_one("#section-list", ListView).focus()

    # ---- panel construction -------------------------------------------

    def _build_section_panels(self) -> None:
        s = settings.current()
        self._build_display(s)
        self._build_filters(s)
        self._build_sessions(s)
        self._build_resume(s)
        self._build_transfer(s)
        self._build_notifications(s)
        self._build_keybindings(s)
        self._build_diagnostics()

    def _panel(self, key: str) -> Vertical:
        return self.query_one(f"#section-{key}", Vertical)

    def _row(self, panel: Vertical, label: str, control, help_text: str = "") -> None:
        row = Horizontal(classes="setting-row")
        panel.mount(row)
        row.mount(Label(label, classes="setting-label"))
        row.mount(control)
        if help_text:
            panel.mount(Label(help_text, classes="setting-help"))

    # ---- Display -------------------------------------------------------

    def _build_display(self, s: settings.Settings) -> None:
        panel = self._panel("display")
        panel.mount(Label("Display", classes="section-heading"))

        theme_select = Select(
            options=[(t, t) for t in settings.THEMES],
            value=s.display.theme if s.display.theme in settings.THEMES else "textual-dark",
            allow_blank=False,
            id="display-theme",
        )
        self._row(panel, "Theme", theme_select)

        logo_switch = Switch(value=s.display.show_logo, id="display-show-logo")
        self._row(panel, "Show logo", logo_switch)

        sort_select = Select(
            options=_SORT_OPTIONS,
            value=s.display.sort_mode,
            allow_blank=False,
            id="display-sort",
        )
        self._row(panel, "Default sort", sort_select)

        preview_switch = Switch(value=s.display.show_preview, id="display-show-preview")
        self._row(panel, "Show preview pane", preview_switch)

        panel.mount(_reset_button("display"))

    # ---- Filters -------------------------------------------------------

    def _build_filters(self, s: settings.Settings) -> None:
        panel = self._panel("filters")
        panel.mount(Label("Filters", classes="section-heading"))

        mem_switch = Switch(value=s.filters.hide_claude_mem, id="filters-hide-mem")
        self._row(
            panel,
            "Hide claude-mem",
            mem_switch,
            help_text="Hides observer sessions under ~/.claude-mem (most are noise).",
        )

        agent_select = Select(
            options=_AGENT_OPTIONS,
            value=_agent_to_choice(s.filters.default_agent),
            allow_blank=False,
            id="filters-default-agent",
        )
        self._row(panel, "Default agent", agent_select)

        panel.mount(Label("Hidden directory prefixes", classes="setting-label"))
        panel.mount(
            Label(
                "One per line. ~ is expanded.",
                classes="setting-help",
            )
        )
        ta = TextArea(
            "\n".join(s.filters.hide_directories),
            id="filters-hide-dirs",
            classes="settings-textarea",
        )
        panel.mount(ta)

        panel.mount(_reset_button("filters"))

    # ---- Sessions ------------------------------------------------------

    def _build_sessions(self, s: settings.Settings) -> None:
        panel = self._panel("sessions")
        panel.mount(Label("Sessions", classes="section-heading"))

        view_select = Select(
            options=_VIEW_OPTIONS,
            value=s.filters.default_view,
            allow_blank=False,
            id="sessions-default-view",
        )
        self._row(panel, "Default view", view_select)

        panel.mount(_reset_button("filters"))

    # ---- Resume --------------------------------------------------------

    def _build_resume(self, s: settings.Settings) -> None:
        panel = self._panel("resume")
        panel.mount(Label("Resume", classes="section-heading"))

        terminal_select = Select(
            options=[(t or "Auto-detect", t) for t in settings.TERMINAL_CHOICES],
            value=s.resume.terminal,
            allow_blank=False,
            id="resume-terminal",
        )
        self._row(panel, "Terminal app", terminal_select)

        yolo = Switch(value=s.resume.yolo_default, id="resume-yolo")
        self._row(
            panel,
            "YOLO by default",
            yolo,
            help_text="Adds --dangerously-skip-permissions to every Claude resume.",
        )

        prefer = Switch(value=s.resume.prefer_ide, id="resume-prefer-ide")
        self._row(
            panel,
            "Prefer IDE over terminal",
            prefer,
            help_text="When jumping to a running session, activate the IDE first.",
        )

        panel.mount(_reset_button("resume"))

    # ---- Transfer ------------------------------------------------------

    def _build_transfer(self, s: settings.Settings) -> None:
        panel = self._panel("transfer")
        panel.mount(Label("Transfer", classes="section-heading"))

        ide_select = Select(
            options=[(c or "Auto", c) for c in settings.TRANSFER_IDE_CHOICES],
            value=s.transfer.target_ide,
            allow_blank=False,
            id="transfer-target-ide",
        )
        self._row(
            panel,
            "Target IDE",
            ide_select,
            help_text="Editor to launch when injecting context into a fresh agent.",
        )

        panel.mount(_reset_button("transfer"))

    # ---- Notifications -------------------------------------------------

    def _build_notifications(self, s: settings.Settings) -> None:
        panel = self._panel("notifications")
        panel.mount(Label("Notifications", classes="section-heading"))

        default_to = Input(
            value=str(s.notifications.default_timeout_s),
            id="notif-default-timeout",
            type="number",
            classes="settings-input-narrow",
        )
        self._row(panel, "Default timeout (s)", default_to)

        error_to = Input(
            value=str(s.notifications.error_timeout_s),
            id="notif-error-timeout",
            type="number",
            classes="settings-input-narrow",
        )
        self._row(panel, "Error timeout (s)", error_to)

        auto = Switch(value=s.notifications.auto_dismiss_errors, id="notif-auto-dismiss")
        self._row(panel, "Auto-dismiss errors", auto)

        panel.mount(_reset_button("notifications"))

    # ---- Keybindings ---------------------------------------------------

    def _build_keybindings(self, s: settings.Settings) -> None:
        panel = self._panel("keybindings")
        panel.mount(Label("Keybindings", classes="section-heading"))
        panel.mount(
            Label(
                "Override individual keys; restart hmd for changes to fully apply.",
                classes="setting-help",
            )
        )

        # Source-of-truth list. (action, default_key, label)
        bindings: list[tuple[str, str, str]] = [
            ("resume_session", "enter", "Resume"),
            ("resume_session_yolo", "shift+enter", "Resume (YOLO)"),
            ("focus_search", "/", "Focus search"),
            ("copy_path", "c", "Copy resume command"),
            ("toggle_pin", "p", "Pin / unpin"),
            ("toggle_claude_mem", "m", "Toggle claude-mem"),
            ("activate_ide", "i", "Jump to IDE"),
            ("transfer", "t", "Open transfer"),
            ("rescan", "r", "Rescan"),
            ("cycle_sort", "o", "Cycle sort"),
            ("settings", "s", "Open settings"),
        ]

        for action, default_key, label in bindings:
            current = s.keybindings.overrides.get(action, default_key)
            row = Horizontal(classes="setting-row")
            panel.mount(row)
            row.mount(Label(label, classes="setting-label"))
            row.mount(Label(current, classes="key-current", id=f"key-current-{action}"))
            row.mount(
                Button(
                    "Capture",
                    classes="capture-btn",
                    id=f"capture-{action}",
                )
            )
            row.mount(
                Button(
                    "Default",
                    classes="capture-btn",
                    id=f"reset-{action}",
                )
            )

        panel.mount(_reset_button("keybindings"))

    # ---- Diagnostics ---------------------------------------------------

    def _build_diagnostics(self) -> None:
        panel = self._panel("diagnostics")
        panel.mount(Label("Diagnostics", classes="section-heading"))

        for label, value in [
            ("Version", __version__),
            ("Config file", str(settings.CONFIG_PATH)),
            ("State DB", str(DB_PATH)),
            ("Index dir", str(INDEX_DIR)),
            ("Log file", str(LOG_FILE)),
        ]:
            row = Horizontal(classes="setting-row")
            panel.mount(row)
            row.mount(Label(label, classes="setting-label"))
            row.mount(Static(value, classes="diag-value"))

        with_btn = Horizontal(classes="setting-row")
        panel.mount(with_btn)
        with_btn.mount(Label("", classes="setting-label"))
        with_btn.mount(Button("Reveal config", id="diag-reveal-config"))
        with_btn.mount(Button("Reveal log", id="diag-reveal-log"))

    # ---- section switching --------------------------------------------

    @on(ListView.Selected, "#section-list")
    def _on_section_selected(self, event: ListView.Selected) -> None:
        if event.item is None or event.item.id is None:
            return
        key = event.item.id.removeprefix("nav-")
        self._show_section(key)

    @on(ListView.Highlighted, "#section-list")
    def _on_section_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item is None or event.item.id is None:
            return
        key = event.item.id.removeprefix("nav-")
        self._show_section(key)

    def _show_section(self, key: str) -> None:
        self.current_section = key
        for k, _ in SECTIONS:
            panel = self._panel(k)
            if k == key:
                panel.remove_class("hidden")
            else:
                panel.add_class("hidden")

    # ---- live-apply hooks ---------------------------------------------

    @on(Switch.Changed)
    def _on_switch(self, event: Switch.Changed) -> None:
        wid = event.switch.id or ""
        s = settings.current()
        section = ""
        field = ""
        if wid == "display-show-logo":
            s.display.show_logo = event.value
            section, field = "display", "show_logo"
        elif wid == "display-show-preview":
            s.display.show_preview = event.value
            section, field = "display", "show_preview"
        elif wid == "filters-hide-mem":
            s.filters.hide_claude_mem = event.value
            section, field = "filters", "hide_claude_mem"
        elif wid == "resume-yolo":
            s.resume.yolo_default = event.value
            section, field = "resume", "yolo_default"
        elif wid == "resume-prefer-ide":
            s.resume.prefer_ide = event.value
            section, field = "resume", "prefer_ide"
        elif wid == "notif-auto-dismiss":
            s.notifications.auto_dismiss_errors = event.value
            section, field = "notifications", "auto_dismiss_errors"
        else:
            return
        settings.update(s)
        self.app.post_message(SettingChanged(section, field, event.value))

    @on(Select.Changed)
    def _on_select(self, event: Select.Changed) -> None:
        wid = event.select.id or ""
        value = event.value
        if value is Select.BLANK:
            return
        s = settings.current()
        section = ""
        field = ""
        if wid == "display-theme":
            s.display.theme = str(value)
            section, field = "display", "theme"
        elif wid == "display-sort":
            s.display.sort_mode = str(value)
            section, field = "display", "sort_mode"
        elif wid == "filters-default-agent":
            s.filters.default_agent = _choice_to_agent(str(value))
            section, field = "filters", "default_agent"
        elif wid == "sessions-default-view":
            s.filters.default_view = str(value)
            section, field = "filters", "default_view"
        elif wid == "resume-terminal":
            s.resume.terminal = str(value)
            section, field = "resume", "terminal"
        elif wid == "transfer-target-ide":
            s.transfer.target_ide = str(value)
            section, field = "transfer", "target_ide"
        else:
            return
        settings.update(s)
        self.app.post_message(SettingChanged(section, field, value))

    @on(Input.Submitted)
    def _on_input_submitted(self, event: Input.Submitted) -> None:
        self._apply_input(event.input.id or "", event.value)

    @on(Input.Blurred)
    def _on_input_blurred(self, event: Input.Blurred) -> None:
        self._apply_input(event.input.id or "", event.input.value)

    def _apply_input(self, wid: str, raw_value: str) -> None:
        s = settings.current()
        try:
            value = float(raw_value)
        except ValueError:
            return
        section = ""
        field = ""
        if wid == "notif-default-timeout":
            s.notifications.default_timeout_s = max(0.5, value)
            section, field = "notifications", "default_timeout_s"
        elif wid == "notif-error-timeout":
            s.notifications.error_timeout_s = max(0.5, value)
            section, field = "notifications", "error_timeout_s"
        else:
            return
        settings.update(s)
        self.app.post_message(SettingChanged(section, field, value))

    @on(TextArea.Changed, "#filters-hide-dirs")
    def _on_hide_dirs_changed(self, event: TextArea.Changed) -> None:
        # Persist on every change — TextArea has no submit, so we can't
        # wait for a save action. The list is small and writes are cheap.
        s = settings.current()
        lines = [line.strip() for line in event.text_area.text.splitlines() if line.strip()]
        s.filters.hide_directories = lines
        settings.update(s)
        self.app.post_message(SettingChanged("filters", "hide_directories", lines))

    # ---- buttons -------------------------------------------------------

    @on(Button.Pressed)
    def _on_button(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid.startswith("reset-section-"):
            section = bid.removeprefix("reset-section-")
            settings.reset_section(section)
            self._refresh_panels()
            self.app.post_message(SettingChanged(section, "*", None))
            return
        if bid == "diag-reveal-config":
            _open_in_finder(str(settings.CONFIG_PATH))
            return
        if bid == "diag-reveal-log":
            _open_in_finder(str(LOG_FILE))
            return
        if bid.startswith("capture-"):
            action = bid.removeprefix("capture-")
            self.app.push_screen(KeyCaptureModal(action), self._on_key_captured)
            return
        if bid.startswith("reset-"):
            action = bid.removeprefix("reset-")
            s = settings.current()
            s.keybindings.overrides.pop(action, None)
            settings.update(s)
            self._refresh_keybinding_label(action)
            self.app.post_message(SettingChanged("keybindings", action, None))
            return

    def _on_key_captured(self, result: tuple[str, str] | None) -> None:
        if result is None:
            return
        action, key = result
        s = settings.current()
        s.keybindings.overrides[action] = key
        settings.update(s)
        self._refresh_keybinding_label(action)
        self.app.post_message(SettingChanged("keybindings", action, key))
        self.notify(
            f"Bound {action!r} to {key!r}; restart hmd to take effect.",
            timeout=4,
        )

    def _refresh_keybinding_label(self, action: str) -> None:
        try:
            label = self.query_one(f"#key-current-{action}", Label)
        except Exception:
            return
        s = settings.current()
        # Source-of-truth defaults map duplicated from _build_keybindings;
        # tiny lookup, fine to inline here.
        defaults = {
            "resume_session": "enter",
            "resume_session_yolo": "shift+enter",
            "focus_search": "/",
            "copy_path": "c",
            "toggle_pin": "p",
            "toggle_claude_mem": "m",
            "activate_ide": "i",
            "transfer": "t",
            "rescan": "r",
            "cycle_sort": "o",
            "settings": "s",
        }
        label.update(s.keybindings.overrides.get(action, defaults.get(action, "?")))

    def _refresh_panels(self) -> None:
        # Tear down and rebuild the section panels after a section reset
        # so on-screen controls reflect the fresh defaults.
        for k, _ in SECTIONS:
            panel = self._panel(k)
            for child in list(panel.children):
                child.remove()
        self._build_section_panels()
        self._show_section(self.current_section)

    # ---- escape --------------------------------------------------------

    def action_dismiss_screen(self) -> None:
        self.dismiss(None)


def _reset_button(section: str) -> Button:
    return Button(
        "Reset section",
        classes="reset-section-btn",
        id=f"reset-section-{section}",
    )


# ---------------------------------------------------------------------------
# KeyCaptureModal
# ---------------------------------------------------------------------------


class KeyCaptureModal(ModalScreen[tuple[str, str] | None]):
    """Tiny modal: 'Press a key' → returns (action, key) on next keypress."""

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]
    CSS = """
    KeyCaptureModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }
    KeyCaptureModal > Vertical {
        width: 40;
        height: 7;
        background: $surface;
        border: thick $accent 80%;
        padding: 1 2;
        align: center middle;
    }
    KeyCaptureModal #cap-title {
        text-align: center;
        text-style: bold;
        width: 100%;
    }
    KeyCaptureModal #cap-hint {
        text-align: center;
        color: $text-muted;
        margin-top: 1;
        width: 100%;
    }
    """

    def __init__(self, action: str) -> None:
        super().__init__()
        self._action = action

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(f"Press a key for: {self._action}", id="cap-title")
            yield Label("Esc to cancel", id="cap-hint")

    def on_key(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.key == "escape":
            return  # let the binding handle it
        # Accept any other key
        self.dismiss((self._action, event.key))
        event.stop()

    def action_cancel(self) -> None:
        self.dismiss(None)
