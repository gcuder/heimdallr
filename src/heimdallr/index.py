"""Tantivy full-text index for sessions."""

from __future__ import annotations

import re
import shutil
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import tantivy

from .config import INDEX_DIR, SCHEMA_VERSION
from .models import Session
from .query import DateFilter, DateOp, Filter

_VERSION_FILE = ".schema_version"


@dataclass
class IndexStats:
    total_sessions: int
    sessions_by_agent: dict[str, int]
    total_messages: int
    oldest_session: datetime | None
    newest_session: datetime | None
    top_directories: list[tuple[str, int, int]]
    index_size_bytes: int
    sessions_today: int
    sessions_this_week: int
    sessions_this_month: int
    sessions_older: int
    total_content_chars: int
    avg_content_chars: int
    avg_messages_per_session: float
    sessions_by_weekday: dict[str, int]
    sessions_by_hour: dict[int, int]
    daily_activity: list[tuple[str, int, int]]
    messages_by_agent: dict[str, int] | None = None
    content_chars_by_agent: dict[str, int] | None = None


class TantivyIndex:
    """Search-of-truth for session data."""

    def __init__(self, index_path: Path = INDEX_DIR) -> None:
        self.index_path = index_path
        self._index: tantivy.Index | None = None
        self._schema: tantivy.Schema | None = None
        self._version_file = index_path / _VERSION_FILE

    # ---- schema + lifecycle ----------------------------------------------

    def _build_schema(self) -> tantivy.Schema:
        b = tantivy.SchemaBuilder()
        b.add_text_field("id", stored=True, tokenizer_name="raw")
        b.add_text_field("title", stored=True)
        b.add_text_field("directory", stored=True, tokenizer_name="raw")
        b.add_text_field("agent", stored=True, tokenizer_name="raw")
        b.add_text_field("content", stored=True)
        b.add_float_field("timestamp", stored=True, indexed=True, fast=True)
        b.add_integer_field("message_count", stored=True)
        b.add_float_field("mtime", stored=True)
        b.add_boolean_field("yolo", stored=True)
        return b.build()

    def _check_version(self) -> bool:
        if not self._version_file.exists():
            return False
        try:
            return int(self._version_file.read_text().strip()) == SCHEMA_VERSION
        except (ValueError, OSError):
            return False

    def _write_version(self) -> None:
        self._version_file.parent.mkdir(parents=True, exist_ok=True)
        self._version_file.write_text(str(SCHEMA_VERSION))

    def _clear(self) -> None:
        self._index = None
        self._schema = None
        if self.index_path.exists():
            shutil.rmtree(self.index_path)

    def _ensure_index(self) -> tantivy.Index:
        if self._index is not None:
            return self._index

        if self.index_path.exists() and not self._check_version():
            self._clear()

        self._schema = self._build_schema()
        if self.index_path.exists():
            self._index = tantivy.Index(self._schema, path=str(self.index_path))
        else:
            self.index_path.mkdir(parents=True, exist_ok=True)
            self._index = tantivy.Index(self._schema, path=str(self.index_path))
            self._write_version()
        return self._index

    # ---- read paths ------------------------------------------------------

    def get_known_sessions(self) -> dict[str, tuple[float, str]]:
        if not self.index_path.exists() or not self._check_version():
            return {}
        index = self._ensure_index()
        index.reload()
        searcher = index.searcher()
        if searcher.num_docs == 0:
            return {}
        known: dict[str, tuple[float, str]] = {}
        results = searcher.search(tantivy.Query.all_query(), limit=searcher.num_docs).hits
        for _score, doc_address in results:
            doc = searcher.doc(doc_address)
            sid = doc.get_first("id")
            mtime = doc.get_first("mtime")
            agent = doc.get_first("agent")
            if sid and mtime is not None and agent:
                known[sid] = (mtime, agent)
        return known

    def get_all_sessions(self) -> list[Session]:
        if not self.index_path.exists() or not self._check_version():
            return []
        index = self._ensure_index()
        index.reload()
        searcher = index.searcher()
        if searcher.num_docs == 0:
            return []
        out: list[Session] = []
        results = searcher.search(tantivy.Query.all_query(), limit=searcher.num_docs).hits
        for _score, doc_address in results:
            doc = searcher.doc(doc_address)
            session = self._doc_to_session(doc)
            if session:
                out.append(session)
        return out

    def get_session_count(self, agent_filter: str | None = None) -> int:
        if not self.index_path.exists() or not self._check_version():
            return 0
        index = self._ensure_index()
        index.reload()
        searcher = index.searcher()
        if agent_filter is None:
            return searcher.num_docs
        schema = index.schema
        q = tantivy.Query.term_query(schema, "agent", agent_filter)
        return searcher.search(q, limit=1).count  # type: ignore[attr-defined]

    def get_stats(self) -> IndexStats:
        empty = IndexStats(
            total_sessions=0,
            sessions_by_agent={},
            total_messages=0,
            oldest_session=None,
            newest_session=None,
            top_directories=[],
            index_size_bytes=0,
            sessions_today=0,
            sessions_this_week=0,
            sessions_this_month=0,
            sessions_older=0,
            total_content_chars=0,
            avg_content_chars=0,
            avg_messages_per_session=0.0,
            sessions_by_weekday={},
            sessions_by_hour={},
            daily_activity=[],
        )
        if not self.index_path.exists() or not self._check_version():
            return empty
        index = self._ensure_index()
        index.reload()
        searcher = index.searcher()
        if searcher.num_docs == 0:
            empty.index_size_bytes = self._get_index_size()
            return empty

        agent_counts: Counter[str] = Counter()
        agent_messages: Counter[str] = Counter()
        agent_content: Counter[str] = Counter()
        dir_counts: Counter[str] = Counter()
        dir_messages: Counter[str] = Counter()
        weekday_counts: Counter[str] = Counter()
        hour_counts: Counter[int] = Counter()
        daily_sessions: Counter[str] = Counter()
        daily_messages: Counter[str] = Counter()
        total_messages = 0
        total_content_chars = 0
        oldest_ts: float | None = None
        newest_ts: float | None = None

        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=today_start.weekday())
        month_start = today_start.replace(day=1)

        sessions_today = sessions_this_week = sessions_this_month = sessions_older = 0
        weekday_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

        results = searcher.search(tantivy.Query.all_query(), limit=searcher.num_docs).hits
        for _score, doc_address in results:
            doc = searcher.doc(doc_address)
            agent = doc.get_first("agent")
            if agent:
                agent_counts[agent] += 1

            directory = doc.get_first("directory")
            if directory:
                dir_counts[directory] += 1

            msg_count = doc.get_first("message_count") or 0
            total_messages += msg_count
            if directory:
                dir_messages[directory] += msg_count
            if agent:
                agent_messages[agent] += msg_count

            content = doc.get_first("content") or ""
            content_len = len(content)
            total_content_chars += content_len
            if agent:
                agent_content[agent] += content_len

            timestamp = doc.get_first("timestamp")
            if timestamp is not None:
                if oldest_ts is None or timestamp < oldest_ts:
                    oldest_ts = timestamp
                if newest_ts is None or timestamp > newest_ts:
                    newest_ts = timestamp
                dt = datetime.fromtimestamp(timestamp)
                if dt >= today_start:
                    sessions_today += 1
                if dt >= week_start:
                    sessions_this_week += 1
                if dt >= month_start:
                    sessions_this_month += 1
                else:
                    sessions_older += 1
                weekday_counts[weekday_names[dt.weekday()]] += 1
                hour_counts[dt.hour] += 1
                date_str = dt.strftime("%Y-%m-%d")
                daily_sessions[date_str] += 1
                if msg_count:
                    daily_messages[date_str] += msg_count

        num_docs = searcher.num_docs
        all_dates = sorted(set(daily_sessions.keys()) | set(daily_messages.keys()))
        daily_activity = [
            (d, daily_sessions.get(d, 0), daily_messages.get(d, 0)) for d in all_dates
        ]

        return IndexStats(
            total_sessions=num_docs,
            sessions_by_agent=dict(agent_counts),
            total_messages=total_messages,
            oldest_session=datetime.fromtimestamp(oldest_ts) if oldest_ts else None,
            newest_session=datetime.fromtimestamp(newest_ts) if newest_ts else None,
            top_directories=[(d, c, dir_messages[d]) for d, c in dir_counts.most_common(10)],
            index_size_bytes=self._get_index_size(),
            sessions_today=sessions_today,
            sessions_this_week=sessions_this_week,
            sessions_this_month=sessions_this_month,
            sessions_older=sessions_older,
            total_content_chars=total_content_chars,
            avg_content_chars=total_content_chars // num_docs if num_docs else 0,
            avg_messages_per_session=total_messages / num_docs if num_docs else 0.0,
            sessions_by_weekday={d: weekday_counts.get(d, 0) for d in weekday_names},
            sessions_by_hour=dict(hour_counts),
            daily_activity=daily_activity,
            messages_by_agent=dict(agent_messages),
            content_chars_by_agent=dict(agent_content),
        )

    def _get_index_size(self) -> int:
        if not self.index_path.exists():
            return 0
        return sum(f.stat().st_size for f in self.index_path.rglob("*") if f.is_file())

    def _doc_to_session(self, doc: tantivy.Document) -> Session | None:
        try:
            sid = doc.get_first("id")
            ts = doc.get_first("timestamp")
            if not sid or ts is None:
                return None
            return Session(
                id=sid,
                agent=doc.get_first("agent") or "",
                title=doc.get_first("title") or "",
                directory=doc.get_first("directory") or "",
                timestamp=datetime.fromtimestamp(ts),
                content=doc.get_first("content") or "",
                message_count=doc.get_first("message_count") or 0,
                mtime=doc.get_first("mtime") or 0.0,
                yolo=doc.get_first("yolo") or False,
            )
        except Exception:
            return None

    # ---- write paths -----------------------------------------------------

    def delete_sessions(self, session_ids: list[str]) -> None:
        if not session_ids:
            return
        index = self._ensure_index()
        writer = index.writer()
        for sid in session_ids:
            writer.delete_documents_by_term("id", sid)
        writer.commit()

    def add_sessions(self, sessions: list[Session]) -> None:
        if not sessions:
            return
        index = self._ensure_index()
        writer = index.writer()
        for s in sessions:
            writer.add_document(self._session_to_doc(s))
        writer.commit()

    def update_sessions(self, sessions: list[Session]) -> None:
        if not sessions:
            return
        index = self._ensure_index()
        writer = index.writer()
        for s in sessions:
            writer.delete_documents_by_term("id", s.id)
        for s in sessions:
            writer.add_document(self._session_to_doc(s))
        writer.commit()

    def _session_to_doc(self, s: Session) -> tantivy.Document:
        return tantivy.Document(
            id=s.id,
            title=s.title,
            directory=s.directory,
            agent=s.agent,
            content=s.content,
            timestamp=s.timestamp.timestamp(),
            message_count=s.message_count,
            mtime=s.mtime,
            yolo=s.yolo,
        )

    # ---- search ----------------------------------------------------------

    def search(
        self,
        query: str,
        agent_filter: Filter | None = None,
        directory_filter: Filter | None = None,
        date_filter: DateFilter | None = None,
        limit: int = 100,
    ) -> list[tuple[str, float]]:
        index = self._ensure_index()
        index.reload()
        searcher = index.searcher()
        schema = index.schema

        try:
            parts: list[tuple[tantivy.Occur, tantivy.Query]] = []

            if query.strip():
                parts.append((tantivy.Occur.Must, self._build_hybrid_query(query, index, schema)))

            agent_q = self._build_agent_filter_query(agent_filter, schema)
            if agent_q:
                parts.append((tantivy.Occur.Must, agent_q))

            dir_q = self._build_directory_filter_query(directory_filter, schema)
            if dir_q:
                parts.append((tantivy.Occur.Must, dir_q))

            date_q = self._build_date_filter_query(date_filter, schema)
            if date_q:
                parts.append((tantivy.Occur.Must, date_q))

            combined = tantivy.Query.boolean_query(parts) if parts else tantivy.Query.all_query()

            if not query.strip():
                results = searcher.search(
                    combined, limit, order_by_field="timestamp", order=tantivy.Order.Desc,
                ).hits
            else:
                results = searcher.search(combined, limit).hits

            out = []
            for score, doc_address in results:
                doc = searcher.doc(doc_address)
                sid = doc.get_first("id")
                if sid:
                    out.append((sid, score))
            return out
        except Exception:
            return []

    def _build_agent_filter_query(
        self, f: Filter | None, schema: tantivy.Schema
    ) -> tantivy.Query | None:
        if not f:
            return None
        parts: list[tuple[tantivy.Occur, tantivy.Query]] = []
        if f.include:
            if len(f.include) == 1:
                inc = tantivy.Query.term_query(schema, "agent", f.include[0])
            else:
                inc = tantivy.Query.term_set_query(schema, "agent", f.include)
            parts.append((tantivy.Occur.Must, inc))
        for ex in f.exclude:
            parts.append((tantivy.Occur.MustNot, tantivy.Query.term_query(schema, "agent", ex)))
        if not parts:
            return None
        if not f.include and f.exclude:
            parts.insert(0, (tantivy.Occur.Must, tantivy.Query.all_query()))
        return tantivy.Query.boolean_query(parts)

    def _build_directory_filter_query(
        self, f: Filter | None, schema: tantivy.Schema
    ) -> tantivy.Query | None:
        if not f:
            return None
        parts: list[tuple[tantivy.Occur, tantivy.Query]] = []
        if f.include:
            inc_parts: list[tuple[tantivy.Occur, tantivy.Query]] = []
            for pat in f.include:
                regex = f"(?i).*{re.escape(pat)}.*"
                inc_parts.append(
                    (tantivy.Occur.Should, tantivy.Query.regex_query(schema, "directory", regex))
                )
            if len(inc_parts) == 1:
                parts.append((tantivy.Occur.Must, inc_parts[0][1]))
            else:
                parts.append((tantivy.Occur.Must, tantivy.Query.boolean_query(inc_parts)))
        for pat in f.exclude:
            regex = f"(?i).*{re.escape(pat)}.*"
            parts.append(
                (tantivy.Occur.MustNot, tantivy.Query.regex_query(schema, "directory", regex))
            )
        if not parts:
            return None
        if not f.include and f.exclude:
            parts.insert(0, (tantivy.Occur.Must, tantivy.Query.all_query()))
        return tantivy.Query.boolean_query(parts)

    def _build_date_filter_query(
        self, f: DateFilter | None, schema: tantivy.Schema
    ) -> tantivy.Query | None:
        if not f:
            return None
        cutoff_ts = f.cutoff.timestamp()

        if f.op == DateOp.LESS_THAN:
            range_q = tantivy.Query.range_query(
                schema, "timestamp", tantivy.FieldType.Float,
                lower_bound=cutoff_ts, upper_bound=float("inf"),
                include_lower=True, include_upper=True,
            )
        elif f.op == DateOp.GREATER_THAN:
            range_q = tantivy.Query.range_query(
                schema, "timestamp", tantivy.FieldType.Float,
                lower_bound=float("-inf"), upper_bound=cutoff_ts,
                include_lower=True, include_upper=False,
            )
        elif f.op == DateOp.EXACT:
            v = f.value.lower()
            if v == "today":
                range_q = tantivy.Query.range_query(
                    schema, "timestamp", tantivy.FieldType.Float,
                    lower_bound=cutoff_ts, upper_bound=float("inf"),
                    include_lower=True, include_upper=True,
                )
            elif v == "yesterday":
                next_day = (f.cutoff + timedelta(days=1)).timestamp()
                range_q = tantivy.Query.range_query(
                    schema, "timestamp", tantivy.FieldType.Float,
                    lower_bound=cutoff_ts, upper_bound=next_day,
                    include_lower=True, include_upper=False,
                )
            else:
                return None
        else:
            return None

        if f.negated:
            return tantivy.Query.boolean_query(
                [
                    (tantivy.Occur.Must, tantivy.Query.all_query()),
                    (tantivy.Occur.MustNot, range_q),
                ]
            )
        return range_q

    def _build_hybrid_query(
        self, query: str, index: tantivy.Index, schema: tantivy.Schema
    ) -> tantivy.Query:
        exact = index.parse_query(query, ["title", "content"])
        boosted_exact = tantivy.Query.boost_query(exact, 5.0)

        fuzzy_parts: list[tuple[tantivy.Occur, tantivy.Query]] = []
        for term in query.split():
            if not term:
                continue
            ft = tantivy.Query.fuzzy_term_query(schema, "title", term, distance=1, prefix=True)
            fc = tantivy.Query.fuzzy_term_query(schema, "content", term, distance=1, prefix=True)
            fuzzy_parts.append(
                (
                    tantivy.Occur.Must,
                    tantivy.Query.boolean_query(
                        [(tantivy.Occur.Should, ft), (tantivy.Occur.Should, fc)]
                    ),
                )
            )
        if fuzzy_parts:
            return tantivy.Query.boolean_query(
                [
                    (tantivy.Occur.Should, boosted_exact),
                    (tantivy.Occur.Should, tantivy.Query.boolean_query(fuzzy_parts)),
                ]
            )
        return boosted_exact
