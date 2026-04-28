"""Highlighter + suggester for keyword search syntax (agent:, dir:, date:)."""

from __future__ import annotations

import re

from rich.highlighter import Highlighter
from rich.text import Text
from textual.suggester import Suggester

from ..config import AGENTS
from .query import KEYWORD_PATTERN, is_valid_filter_value


class KeywordHighlighter(Highlighter):
    def highlight(self, text: Text) -> None:
        plain = text.plain
        for match in KEYWORD_PATTERN.finditer(plain):
            neg = match.group(1)
            keyword = match.group(2)
            value = match.group(3)
            valid = is_valid_filter_value(keyword, value)

            if neg:
                text.stylize("bold red", match.start(1), match.end(1))
            text.stylize(
                "bold cyan" if valid else "bold red", match.start(2), match.end(2)
            )
            if not valid:
                text.stylize("red strike", match.start(3), match.end(3))
            elif value.startswith("!"):
                text.stylize("bold red", match.start(3), match.start(3) + 1)
                text.stylize("green", match.start(3) + 1, match.end(3))
            else:
                text.stylize("green", match.start(3), match.end(3))


_PARTIAL_KEYWORD_PATTERN = re.compile(r"(-?)(agent:|dir:|date:)([^\s]*)$")
_KEYWORD_VALUES = {
    "agent:": list(AGENTS.keys()),
    "date:": ["today", "yesterday", "week", "month"],
}


class KeywordSuggester(Suggester):
    def __init__(self) -> None:
        super().__init__(use_cache=True, case_sensitive=False)

    async def get_suggestion(self, value: str) -> str | None:
        match = _PARTIAL_KEYWORD_PATTERN.search(value)
        if not match:
            return None
        keyword = match.group(2)
        partial = match.group(3)
        known = _KEYWORD_VALUES.get(keyword)
        if not known or not partial:
            return None
        negated = partial.startswith("!")
        search_partial = partial[1:] if negated else partial
        for candidate in known:
            if (
                candidate.lower().startswith(search_partial.lower())
                and candidate.lower() != search_partial.lower()
            ):
                suggested = f"!{candidate}" if negated else candidate
                return value[: match.start(3)] + suggested
        return None
