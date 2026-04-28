"""Query parsing helpers used by the search input + filter bar."""

from __future__ import annotations

import re

from ..config import AGENTS

KEYWORD_PATTERN = re.compile(r"(-?)(agent:|dir:|date:)(\S+)")
AGENT_KEYWORD_PATTERN = re.compile(r"-?agent:(\S+)")
VALID_DATE_KEYWORDS = {"today", "yesterday", "week", "month"}
DATE_PATTERN = re.compile(r"^([<>])?(\d+)(m|h|d|w|mo|y)$")


def is_valid_filter_value(keyword: str, value: str) -> bool:
    check_value = value.lstrip("!")
    values = [v.strip().lstrip("!") for v in check_value.split(",") if v.strip()]
    if keyword == "agent:":
        return all(v.lower() in AGENTS for v in values)
    if keyword == "date:":
        for v in values:
            v_lower = v.lower()
            if v_lower not in VALID_DATE_KEYWORDS and not DATE_PATTERN.match(v_lower):
                return False
        return True
    if keyword == "dir:":
        return True
    return True


def extract_agent_from_query(query: str) -> str | None:
    match = AGENT_KEYWORD_PATTERN.search(query)
    if not match:
        return None
    if match.group(0).startswith("-"):
        return None
    value = match.group(1)
    if value.startswith("!"):
        return None
    for v in value.split(","):
        v = v.strip()
        if v and not v.startswith("!"):
            return v
    return None


def update_agent_in_query(query: str, agent: str | None) -> str:
    cleaned = " ".join(AGENT_KEYWORD_PATTERN.sub("", query).split())
    if agent is None:
        return cleaned
    return f"{cleaned} agent:{agent}".strip()
