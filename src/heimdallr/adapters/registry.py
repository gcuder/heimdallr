"""Adapter registry — single source of truth for tool name → adapter mapping."""

from __future__ import annotations

from .base import ToolAdapter
from .claude import ClaudeAdapter
from .codex import CodexAdapter

_REGISTRY: dict[str, type[ToolAdapter]] = {
    ClaudeAdapter.name: ClaudeAdapter,
    CodexAdapter.name: CodexAdapter,
}


def get_adapter(name: str) -> ToolAdapter | None:
    cls = _REGISTRY.get(name)
    return cls() if cls else None


def get_all_adapters() -> list[ToolAdapter]:
    return [cls() for cls in _REGISTRY.values()]
