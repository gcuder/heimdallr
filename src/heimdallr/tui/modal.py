"""Modal screens — yolo confirmation."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label

from .styles import YOLO_MODAL_CSS


class YoloModeModal(ModalScreen[bool]):
    BINDINGS = [
        Binding("y", "select_yolo", "Yolo", show=False),
        Binding("n", "select_normal", "Normal", show=False),
        Binding("escape", "dismiss", "Cancel", show=False),
        Binding("enter", "select_focused", "Select", show=False),
        Binding("left", "focus_normal", "Left", show=False),
        Binding("right", "focus_yolo", "Right", show=False),
    ]
    CSS = YOLO_MODAL_CSS

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Resume with yolo mode?", id="title")
            with Horizontal(id="buttons"):
                yield Button("No", id="normal-btn")
                yield Button("Yolo", id="yolo-btn")

    def on_mount(self) -> None:
        self.query_one("#normal-btn", Button).focus()

    def action_toggle_focus(self) -> None:
        if self.focused and self.focused.id == "yolo-btn":
            self.query_one("#normal-btn", Button).focus()
        else:
            self.query_one("#yolo-btn", Button).focus()

    def action_focus_normal(self) -> None:
        self.query_one("#normal-btn", Button).focus()

    def action_focus_yolo(self) -> None:
        self.query_one("#yolo-btn", Button).focus()

    def action_select_focused(self) -> None:
        f = self.focused
        self.dismiss(bool(f and f.id == "yolo-btn"))

    def action_select_yolo(self) -> None:
        self.dismiss(True)

    def action_select_normal(self) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#yolo-btn")
    def on_yolo_pressed(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#normal-btn")
    def on_normal_pressed(self) -> None:
        self.dismiss(False)
