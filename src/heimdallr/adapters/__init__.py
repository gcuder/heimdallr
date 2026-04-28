"""Adapters for Claude Code and Codex sessions."""

from .base import BaseSessionAdapter, ErrorCallback, SessionCallback, ToolAdapter, truncate_title
from .claude import ClaudeAdapter
from .codex import CodexAdapter
from .registry import get_adapter, get_all_adapters

__all__ = [
    "BaseSessionAdapter",
    "ClaudeAdapter",
    "CodexAdapter",
    "ErrorCallback",
    "SessionCallback",
    "ToolAdapter",
    "get_adapter",
    "get_all_adapters",
    "truncate_title",
]
