"""Single-screen modal that previews and confirms a context transfer.

User picks: target tool (claude/codex) + strategy (summary/hybrid/full).
We show a live token estimate so they can size the transfer before executing.
"""

from __future__ import annotations

from dataclasses import dataclass

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, RadioButton, RadioSet

from ..models import Session
from ..transfer import ContextBundle, Strategy, compact
from .styles import TRANSFER_MODAL_CSS


@dataclass
class TransferResult:
    bundle: ContextBundle
    target_agent: str


class TransferModal(ModalScreen["TransferResult | None"]):
    """Pick a strategy + target tool. Returns a ContextBundle on Execute, or None on cancel."""

    BINDINGS = [
        Binding("escape", "dismiss_none", "Cancel", show=False),
        Binding("enter", "execute", "Execute", show=False, priority=True),
    ]
    CSS = TRANSFER_MODAL_CSS

    def __init__(self, source: Session) -> None:
        super().__init__()
        self.source = source
        self._target_agent: str = source.agent  # default: same tool
        self._strategy: Strategy = "hybrid"
        self._bundle_cache: dict[Strategy, ContextBundle] = {}

    def _bundle_for(self, strategy: Strategy) -> ContextBundle:
        cached = self._bundle_cache.get(strategy)
        if cached is not None:
            return cached
        bundle = compact(self.source, strategy)
        self._bundle_cache[strategy] = bundle
        return bundle

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("Transfer context from this session", id="title")
            yield Label(
                f"Source: {self.source.agent} · {self.source.title[:48]}"
                f"  ({self.source.message_count} turns)",
            )

            yield Label("Strategy", classes="section-label")
            with RadioSet(id="strategy"):
                yield RadioButton("Summary  — title + first/last user message", id="strategy-summary")
                yield RadioButton(
                    "Hybrid   — summary + last 4 turns (recommended)",
                    value=True,
                    id="strategy-hybrid",
                )
                yield RadioButton("Full     — entire transcript (may be capped)", id="strategy-full")

            yield Label("Target tool", classes="section-label")
            with RadioSet(id="target"):
                yield RadioButton(
                    "claude",
                    value=self.source.agent == "claude",
                    id="target-claude",
                )
                yield RadioButton(
                    "codex",
                    value=self.source.agent == "codex",
                    id="target-codex",
                )

            yield Label("", id="estimate")

            with Horizontal(id="buttons"):
                yield Button("Cancel", id="cancel-btn")
                yield Button("Execute →", id="execute-btn", variant="primary")

    def on_mount(self) -> None:
        self._refresh_estimate()
        self.query_one("#execute-btn", Button).focus()

    @on(RadioSet.Changed, "#strategy")
    def _on_strategy(self, event: RadioSet.Changed) -> None:
        idx = event.radio_set.pressed_index
        self._strategy = ["summary", "hybrid", "full"][idx]
        self._refresh_estimate()

    @on(RadioSet.Changed, "#target")
    def _on_target(self, event: RadioSet.Changed) -> None:
        idx = event.radio_set.pressed_index
        self._target_agent = ["claude", "codex"][idx]
        self._refresh_estimate()

    def _refresh_estimate(self) -> None:
        bundle = self._bundle_for(self._strategy)
        from ..transfer.injector import INLINE_TOKEN_LIMIT

        method = "file" if bundle.token_count > INLINE_TOKEN_LIMIT else "inline"
        self.query_one("#estimate", Label).update(
            f"~{bundle.token_count:,} tokens → {self._target_agent} via {method}"
        )

    @on(Button.Pressed, "#cancel-btn")
    def _on_cancel(self) -> None:
        self.dismiss(None)

    def action_dismiss_none(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#execute-btn")
    def _on_execute(self) -> None:
        self.action_execute()

    def action_execute(self) -> None:
        bundle = self._bundle_for(self._strategy)
        self.dismiss(TransferResult(bundle=bundle, target_agent=self._target_agent))
