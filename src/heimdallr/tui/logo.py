"""Heimdallr logo widget for the TUI title bar.

Uses `textual-image`'s Sixel renderer — pixel-perfect inside iTerm2 and
other Sixel-capable terminals. (Direct OSC 1337 inline images don't work
reliably from Textual: large escape payloads get fragmented and the
alternate-screen buffer interacts badly with the protocol. Sixel is
streaming-friendly and handles alt-screen properly.)

On terminals that don't support Sixel (Apple Terminal, VS Code) the
widget falls back to a half-cell unicode rendering — still recognisable.
"""

from __future__ import annotations

import importlib.resources
import logging

from rich.text import Text
from textual.widget import Widget
from textual_image.widget import Image as ImageWidget

logger = logging.getLogger(__name__)


def _logo_path() -> str | None:
    try:
        ref = importlib.resources.files("heimdallr.assets") / "logo.png"
        return str(ref)
    except (FileNotFoundError, ModuleNotFoundError, OSError) as e:
        logger.warning("logo asset not found: %s", e)
        return None


class LogoWidget(Widget):
    """Renders the heimdallr logo in the title bar via textual-image."""

    DEFAULT_CSS = """
    LogoWidget { width: auto; height: auto; }
    LogoWidget Image { width: 4; height: 4; }
    """

    def compose(self):
        path = _logo_path()
        if path is None:
            from textual.widgets import Static

            yield Static(Text("⚔", style="bold #d4af37"))
            return
        # AutoImage in textual-image picks the best protocol for the
        # terminal (TGP for kitty/wezterm, Sixel for iTerm2/foot/etc.,
        # halfcell fallback). Image is the alias for AutoImage.
        yield ImageWidget(path, id="logo-img")
