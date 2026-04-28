"""Query parser for keyword-based search syntax.

Supports `agent:claude,codex dir:my-project date:<1d api auth`.

Keywords:
- agent: filter by agent name (multi: agent:claude,codex)
- dir: filter by directory substring (multi: dir:proj1,proj2)
- date: filter by date (today, yesterday, <1h, >1d, week, month)

Negation:
- ! prefix on value: agent:!claude
- - prefix on keyword: -agent:claude
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum


class DateOp(Enum):
    EXACT = "exact"
    LESS_THAN = "<"
    GREATER_THAN = ">"


@dataclass
class DateFilter:
    op: DateOp
    value: str
    cutoff: datetime
    negated: bool = False


@dataclass
class Filter:
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)

    @property
    def values(self) -> list[str]:
        return self.include + self.exclude

    @property
    def negated(self) -> bool:
        return len(self.include) == 0 and len(self.exclude) > 0

    def matches(self, value: str, substring: bool = False) -> bool:
        if not self.include and not self.exclude:
            return True

        def check(filter_val: str) -> bool:
            if substring:
                return filter_val.lower() in value.lower()
            return value == filter_val

        if any(check(v) for v in self.exclude):
            return False
        if not self.include:
            return True
        return any(check(v) for v in self.include)


@dataclass
class ParsedQuery:
    text: str
    agent: Filter | None
    directory: Filter | None
    date: DateFilter | None


_KEYWORD_PATTERN = re.compile(
    r"(-?)(agent|dir|date):"
    r'(?:"([^"]+)"|(\S+))'
)

_RELATIVE_TIME_PATTERN = re.compile(r"^([<>])?(\d+)(m|h|d|w|mo|y)$")

_TIME_UNITS = {
    "m": 60,
    "h": 3600,
    "d": 86400,
    "w": 604800,
    "mo": 2592000,
    "y": 31536000,
}


def _parse_date_value(value: str, negated: bool = False) -> DateFilter | None:
    now = datetime.now()
    if value.startswith("!"):
        value = value[1:]
        negated = True

    v = value.lower()
    if v == "today":
        cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return DateFilter(DateOp.EXACT, value, cutoff, negated)
    if v == "yesterday":
        cutoff = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return DateFilter(DateOp.EXACT, value, cutoff, negated)
    if v == "week":
        return DateFilter(DateOp.LESS_THAN, value, now - timedelta(days=7), negated)
    if v == "month":
        return DateFilter(DateOp.LESS_THAN, value, now - timedelta(days=30), negated)

    m = _RELATIVE_TIME_PATTERN.match(v)
    if m:
        op_str, num_str, unit = m.groups()
        cutoff = now - timedelta(seconds=int(num_str) * _TIME_UNITS[unit])
        if op_str == ">":
            return DateFilter(DateOp.GREATER_THAN, value, cutoff, negated)
        return DateFilter(DateOp.LESS_THAN, value, cutoff, negated)

    return None


def _parse_filter_value(value: str, negated: bool) -> Filter:
    include: list[str] = []
    exclude: list[str] = []
    for raw in (v.strip() for v in value.split(",") if v.strip()):
        if raw.startswith("!"):
            exclude.append(raw[1:])
        elif negated:
            exclude.append(raw)
        else:
            include.append(raw)
    return Filter(include=include, exclude=exclude)


def parse_query(query: str) -> ParsedQuery:
    agent: Filter | None = None
    directory: Filter | None = None
    date: DateFilter | None = None

    for m in _KEYWORD_PATTERN.finditer(query):
        neg = m.group(1) == "-"
        keyword = m.group(2)
        value = m.group(3) or m.group(4)
        if keyword == "agent":
            agent = _parse_filter_value(value, neg)
        elif keyword == "dir":
            directory = _parse_filter_value(value, neg)
        elif keyword == "date":
            date = _parse_date_value(value, neg)

    text = " ".join(_KEYWORD_PATTERN.sub("", query).split())
    return ParsedQuery(text=text, agent=agent, directory=directory, date=date)
