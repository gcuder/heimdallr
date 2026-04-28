"""Aggregator on top of TantivyIndex — orchestrates adapters + index."""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from .adapters import ToolAdapter, get_all_adapters
from .adapters.base import ErrorCallback
from .index import TantivyIndex
from .models import Session
from .query import Filter, parse_query


class SessionSearch:
    """Aggregates sessions from all adapters and answers searches via Tantivy."""

    def __init__(self) -> None:
        self.adapters: list[ToolAdapter] = get_all_adapters()
        self._sessions: list[Session] | None = None
        self._sessions_by_id: dict[str, Session] = {}
        self._streaming_in_progress: bool = False
        self._index = TantivyIndex()

    @property
    def index(self) -> TantivyIndex:
        return self._index

    # ---- index sync ------------------------------------------------------

    def _load_from_index(self) -> list[Session] | None:
        known = self._index.get_known_sessions()
        if not known:
            return None
        for adapter in self.adapters:
            new_or_modified, deleted_ids = adapter.find_sessions_incremental(known)
            if new_or_modified or deleted_ids:
                return None
        sessions = self._index.get_all_sessions()
        if not sessions:
            return None
        for s in sessions:
            self._sessions_by_id[s.id] = s
        return sessions

    def get_all_sessions(self, force_refresh: bool = False) -> list[Session]:
        if self._sessions is not None and not force_refresh:
            return self._sessions
        if self._streaming_in_progress:
            return self._sessions if self._sessions is not None else []

        known = self._index.get_known_sessions() if not force_refresh else {}

        all_new: list[Session] = []
        all_deleted: list[str] = []

        with ThreadPoolExecutor(max_workers=max(1, len(self.adapters))) as pool:
            for new_or_modified, deleted_ids in pool.map(
                lambda a: a.find_sessions_incremental(known), self.adapters
            ):
                all_new.extend(new_or_modified)
                all_deleted.extend(deleted_ids)

        if not all_new and not all_deleted and known:
            self._sessions = self._index.get_all_sessions()
            for s in self._sessions:
                self._sessions_by_id[s.id] = s
            self._sessions.sort(key=lambda s: s.timestamp, reverse=True)
            return self._sessions

        self._index.delete_sessions(all_deleted)
        self._index.update_sessions(all_new)

        self._sessions = self._index.get_all_sessions()
        for s in self._sessions:
            self._sessions_by_id[s.id] = s
        self._sessions.sort(key=lambda s: s.timestamp, reverse=True)
        return self._sessions

    def index_sessions_parallel(
        self,
        on_progress: Callable[[], None],
        on_error: ErrorCallback = None,
        batch_size: int = 100,
    ) -> tuple[list[Session], int, int, int]:
        known = self._index.get_known_sessions()

        existing = self._index.get_all_sessions()
        for s in existing:
            self._sessions_by_id[s.id] = s
        if existing:
            on_progress()

        self._streaming_in_progress = True
        total_new = total_updated = total_deleted = 0

        lock = threading.Lock()
        pending: list[Session] = []
        all_deleted_ids: list[str] = []
        sessions_since_progress = 0

        def flush_pending() -> None:
            nonlocal pending
            if pending:
                self._index.update_sessions(pending)
                pending = []

        def handle_session(session: Session) -> None:
            nonlocal total_new, total_updated, sessions_since_progress
            with lock:
                self._sessions_by_id[session.id] = session
                pending.append(session)
                if session.id in known:
                    total_updated += 1
                else:
                    total_new += 1
                sessions_since_progress += 1
                if sessions_since_progress >= batch_size:
                    sessions_since_progress = 0
                    flush_pending()
                    on_progress()

        def get_incremental(adapter: ToolAdapter):
            return adapter.find_sessions_incremental(
                known, on_error=on_error, on_session=handle_session
            )

        try:
            with ThreadPoolExecutor(max_workers=max(1, len(self.adapters))) as pool:
                futures = {pool.submit(get_incremental, a): a for a in self.adapters}
                for fut in as_completed(futures):
                    _new_or_modified, deleted_ids = fut.result()
                    with lock:
                        flush_pending()
                        if deleted_ids:
                            all_deleted_ids.extend(deleted_ids)
                            for sid in deleted_ids:
                                self._sessions_by_id.pop(sid, None)
                            total_deleted += len(deleted_ids)
        finally:
            with lock:
                flush_pending()
            if all_deleted_ids:
                self._index.delete_sessions(all_deleted_ids)
            self._streaming_in_progress = False

        self._sessions = self._index.get_all_sessions()
        for s in self._sessions:
            self._sessions_by_id[s.id] = s
        self._sessions.sort(key=lambda s: s.timestamp, reverse=True)
        return self._sessions, total_new, total_updated, total_deleted

    # ---- queries ---------------------------------------------------------

    def search(
        self,
        query: str,
        agent_filter: str | None = None,
        directory_filter: str | None = None,
        limit: int = 100,
    ) -> list[Session]:
        parsed = parse_query(query)
        text = parsed.text

        eff_agent: Filter | None = (
            Filter(include=[agent_filter]) if agent_filter is not None else parsed.agent
        )
        eff_dir: Filter | None = (
            Filter(include=[directory_filter]) if directory_filter is not None else parsed.directory
        )

        if not self._streaming_in_progress and self._sessions is None:
            self.get_all_sessions()

        results = self._index.search(
            text,
            agent_filter=eff_agent,
            directory_filter=eff_dir,
            date_filter=parsed.date,
            limit=limit,
        )

        out: list[Session] = []
        for sid, _score in results:
            s = self._sessions_by_id.get(sid)
            if s:
                out.append(s)
        return out

    def get_session_count(self, agent_filter: str | None = None) -> int:
        return self._index.get_session_count(agent_filter)

    def get_agents_with_sessions(self) -> set[str]:
        return {a.name for a in self.adapters if self._index.get_session_count(a.name) > 0}

    def get_adapter_for_session(self, session: Session) -> ToolAdapter | None:
        for a in self.adapters:
            if a.name == session.agent:
                return a
        return None

    def get_resume_command(self, session: Session, yolo: bool = False) -> list[str]:
        a = self.get_adapter_for_session(session)
        return a.get_resume_command(session, yolo=yolo) if a else []
