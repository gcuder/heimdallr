"""Pydantic / dataclass models shared across heimdallr modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass
class Session:
    """A coding-agent session — Claude Code or Codex."""

    id: str
    agent: str
    title: str
    directory: str
    timestamp: datetime
    content: str = ""
    message_count: int = 0
    mtime: float = 0.0
    yolo: bool = False


@dataclass
class RawAdapterStats:
    agent: str
    data_dir: str
    available: bool
    file_count: int
    total_bytes: int


@dataclass
class ParseError:
    agent: str
    file_path: str
    error_type: str
    message: str


@dataclass
class RunningInfo:
    """Live state of a session — derived per-tick by RunningDetector."""

    is_running: bool
    confidence: Literal["high", "medium", "low"]
    pid: int | None = None
    started_at: datetime | None = None
    source: list[str] = field(default_factory=list)
    ide: str | None = None
    ide_pid: int | None = None
