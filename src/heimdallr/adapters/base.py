"""Base protocol and abstract class for tool adapters."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from ..logging_config import log_parse_error
from ..models import ParseError, RawAdapterStats, Session

logger = logging.getLogger(__name__)

# 1ms tolerance — datetime / float roundtrip can drop sub-millisecond precision.
MTIME_TOLERANCE = 0.001

ErrorCallback = Callable[[ParseError], None] | None
SessionCallback = Callable[[Session], None] | None


def truncate_title(text: str, max_length: int = 100, word_break: bool = True) -> str:
    text = text.strip()
    if len(text) <= max_length:
        return text
    truncated = text[:max_length]
    if word_break:
        truncated = truncated.rsplit(" ", 1)[0]
    return truncated + "..."


class ToolAdapter(Protocol):
    """Public surface every tool adapter exposes to the rest of heimdallr."""

    name: str
    color: str
    badge: str
    supports_yolo: bool

    def is_available(self) -> bool: ...

    def find_sessions(self) -> list[Session]: ...

    def find_sessions_incremental(
        self,
        known: dict[str, tuple[float, str]],
        on_error: ErrorCallback = None,
        on_session: SessionCallback = None,
    ) -> tuple[list[Session], list[str]]: ...

    def get_resume_command(self, session: Session, yolo: bool = False) -> list[str]: ...

    def build_inject_command(
        self,
        ctx: str,
        target_id: str | None,
        cwd: str | None,
        method: str,
    ) -> list[str]: ...

    def process_match(self, proc: Any) -> tuple[str | None, str]:
        """Map a psutil.Process to a session id.

        Returns (session_id_or_None, confidence) where confidence is "high" or "medium".
        """
        ...

    def get_raw_stats(self) -> RawAdapterStats: ...


class BaseSessionAdapter(ABC):
    """Template-method base for file-based adapters.

    Subclasses implement `_scan_session_files`, `_parse_session_file`,
    `find_sessions`, `get_resume_command`, `build_inject_command`, `process_match`.
    """

    name: str
    color: str
    badge: str
    supports_yolo: bool = False
    _sessions_dir: Path

    def is_available(self) -> bool:
        return self._sessions_dir.exists()

    @abstractmethod
    def _scan_session_files(self) -> dict[str, tuple[Path, float]]: ...

    @abstractmethod
    def _parse_session_file(
        self, session_file: Path, on_error: ErrorCallback = None
    ) -> Session | None: ...

    @abstractmethod
    def find_sessions(self) -> list[Session]: ...

    @abstractmethod
    def get_resume_command(self, session: Session, yolo: bool = False) -> list[str]: ...

    @abstractmethod
    def build_inject_command(
        self,
        ctx: str,
        target_id: str | None,
        cwd: str | None,
        method: str,
    ) -> list[str]: ...

    @abstractmethod
    def process_match(self, proc: Any) -> tuple[str | None, str]: ...

    def find_sessions_incremental(
        self,
        known: dict[str, tuple[float, str]],
        on_error: ErrorCallback = None,
        on_session: SessionCallback = None,
    ) -> tuple[list[Session], list[str]]:
        if not self.is_available():
            deleted_ids = [sid for sid, (_, agent) in known.items() if agent == self.name]
            return [], deleted_ids

        current_files = self._scan_session_files()

        new_or_modified: list[Session] = []
        for session_id, (path, mtime) in current_files.items():
            known_entry = known.get(session_id)
            if known_entry is None or mtime > known_entry[0] + MTIME_TOLERANCE:
                session = self._parse_session_file(path, on_error=on_error)
                if session:
                    session.mtime = mtime
                    new_or_modified.append(session)
                    if on_session:
                        on_session(session)

        current_ids = set(current_files.keys())
        deleted_ids = [
            sid
            for sid, (_, agent) in known.items()
            if agent == self.name and sid not in current_ids
        ]
        return new_or_modified, deleted_ids

    def _record_error(
        self,
        session_file: Path,
        error_type: str,
        message: str,
        on_error: ErrorCallback,
    ) -> None:
        log_parse_error(self.name, str(session_file), error_type, message)
        if on_error:
            on_error(
                ParseError(
                    agent=self.name,
                    file_path=str(session_file),
                    error_type=error_type,
                    message=message,
                )
            )

    def get_raw_stats(self) -> RawAdapterStats:
        if not self.is_available():
            return RawAdapterStats(
                agent=self.name,
                data_dir=str(self._sessions_dir),
                available=False,
                file_count=0,
                total_bytes=0,
            )
        files = self._scan_session_files()
        total_bytes = 0
        for path, _ in files.values():
            try:
                total_bytes += path.stat().st_size
            except OSError:
                pass
        return RawAdapterStats(
            agent=self.name,
            data_dir=str(self._sessions_dir),
            available=True,
            file_count=len(files),
            total_bytes=total_bytes,
        )
