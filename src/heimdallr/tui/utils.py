"""Shared TUI helpers — formatting, icons, clipboard, color gradient."""

from __future__ import annotations

import math
import subprocess
import sys
from datetime import datetime

import humanize
from rich.console import RenderableType
from rich.text import Text

from ..config import AGENTS


def get_agent_icon(agent: str, running: bool = False, low_confidence: bool = False) -> RenderableType:
    """Return a colored agent badge with an optional running dot.

    `● claude` (green dot when running, dim when low_confidence, none otherwise),
    or just the colored badge name.
    """
    cfg = AGENTS.get(agent, {"color": "white", "badge": agent})
    color = cfg["color"]
    badge = cfg["badge"]

    text = Text()
    if running and not low_confidence:
        text.append("● ", style="bold #4ade80")  # green
    elif running and low_confidence:
        text.append("◌ ", style="dim #facc15")  # dim yellow
    else:
        text.append("  ")
    text.append(badge, style=color)
    return text


def format_time_ago(dt: datetime) -> str:
    return humanize.naturaltime(dt)


def format_directory(path: str) -> str:
    if not path:
        return "n/a"
    # Use Path.relative_to so `/Users/foobar` doesn't get rewritten when the
    # home is `/Users/foo` (a substring `startswith` would falsely match).
    try:
        from pathlib import Path

        return "~/" + str(Path(path).relative_to(Path.home()))
    except ValueError:
        return path


def highlight_matches(
    text: str, query: str, max_len: int | None = None, style: str = "bold reverse"
) -> Text:
    if max_len and len(text) > max_len:
        text = text[: max_len - 3] + "..."
    if not query:
        return Text(text)

    result = Text(text)
    text_lower = text.lower()
    for term in query.lower().split():
        if not term:
            continue
        start = 0
        while True:
            idx = text_lower.find(term, start)
            if idx == -1:
                break
            result.stylize(style, idx, idx + len(term))
            start = idx + 1
    return result


def get_age_color(age_hours: float) -> str:
    """Hex color from green → yellow → orange → dim gray as age grows."""
    decay_rate = -math.log(1 - 0.3) / 24
    t = 1 - math.exp(-decay_rate * age_hours)
    if t < 0.3:
        s = t / 0.3
        r = int(100 + s * 100)
        g = int(200 - s * 20)
        b = int(50 - s * 50)
    elif t < 0.6:
        s = (t - 0.3) / 0.3
        r = 200
        g = int(180 - s * 80)
        b = int(s * 50)
    else:
        s = (t - 0.6) / 0.4
        r = int(200 - s * 100)
        g = 100
        b = int(50 + s * 50)
    return f"#{r:02x}{g:02x}{b:02x}"


def copy_to_clipboard(text: str) -> bool:
    try:
        if sys.platform == "darwin":
            subprocess.run(["pbcopy"], input=text.encode(), check=True)
        elif sys.platform == "win32":
            subprocess.run(["clip"], input=text.encode(), check=True)
        else:
            try:
                subprocess.run(
                    ["xclip", "-selection", "clipboard"], input=text.encode(), check=True
                )
            except FileNotFoundError:
                subprocess.run(
                    ["xsel", "--clipboard", "--input"], input=text.encode(), check=True
                )
        return True
    except Exception:
        return False
