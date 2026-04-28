"""Tests for the keyword search query parser."""

from heimdallr.query import DateOp, parse_query


def test_parse_simple_text() -> None:
    p = parse_query("api auth")
    assert p.text == "api auth"
    assert p.agent is None
    assert p.directory is None
    assert p.date is None


def test_parse_agent() -> None:
    p = parse_query("agent:claude api")
    assert p.text == "api"
    assert p.agent is not None
    assert p.agent.include == ["claude"]


def test_parse_agent_negation() -> None:
    p = parse_query("-agent:codex hello")
    assert p.text == "hello"
    assert p.agent is not None
    assert p.agent.exclude == ["codex"]


def test_parse_date_relative() -> None:
    p = parse_query("date:<1h")
    assert p.date is not None
    assert p.date.op == DateOp.LESS_THAN


def test_parse_date_today() -> None:
    p = parse_query("date:today work")
    assert p.text == "work"
    assert p.date is not None
    assert p.date.op == DateOp.EXACT
    assert p.date.value.lower() == "today"


def test_parse_dir() -> None:
    p = parse_query("dir:project foo")
    assert p.text == "foo"
    assert p.directory is not None
    assert p.directory.include == ["project"]


def test_parse_combined() -> None:
    p = parse_query("agent:claude,codex dir:api date:<1d service")
    assert p.text == "service"
    assert p.agent is not None
    assert set(p.agent.include) == {"claude", "codex"}
    assert p.directory is not None
    assert p.directory.include == ["api"]
    assert p.date is not None
