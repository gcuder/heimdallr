"""Compact a session's content into a context bundle.

We do *not* call an LLM. Three mechanical strategies:

- **summary**: title + first user message + last user message. Tiny — a few
  hundred tokens at most. Tells the new session "we started here, ended here".
- **hybrid**: summary + the last N turn-pairs verbatim. ~1-3k tokens.
- **full**: the whole transcript, capped at MAX_FULL_TOKENS so we don't
  inadvertently inject a massive prompt.

`ContextBundle.token_count` uses tiktoken's cl100k_base encoder. Claude's
real tokenizer differs by ~10% — close enough for showing an estimate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import tiktoken

from ..models import Session

Strategy = Literal["summary", "hybrid", "full"]

# Caps to keep injected context manageable.
MAX_FULL_TOKENS = 50_000
HYBRID_TURN_PAIRS = 4

_ENCODER: tiktoken.Encoding | None = None


def _encoder() -> tiktoken.Encoding:
    global _ENCODER
    if _ENCODER is None:
        _ENCODER = tiktoken.get_encoding("cl100k_base")
    return _ENCODER


def _count_tokens(text: str) -> int:
    return len(_encoder().encode(text))


@dataclass
class ContextBundle:
    text: str
    token_count: int
    strategy: Strategy
    source_session_id: str
    source_agent: str


# ---- helpers ----------------------------------------------------------------


def _split_messages(content: str) -> list[str]:
    """Split a session's stored content into individual messages.

    Adapters store sessions as `\n\n`-separated messages with `» ` prefix for
    user turns and `  ` (two-space indent) for assistant turns.
    """
    return [m for m in content.split("\n\n") if m.strip()]


def _first_and_last_user(messages: list[str]) -> tuple[str | None, str | None]:
    user_msgs = [m for m in messages if m.startswith("» ")]
    first = user_msgs[0][2:].strip() if user_msgs else None
    last = user_msgs[-1][2:].strip() if user_msgs else None
    return first, last


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


# ---- strategies -------------------------------------------------------------


def _summary(session: Session) -> str:
    msgs = _split_messages(session.content)
    first, last = _first_and_last_user(msgs)
    parts = [
        f"# Context from a previous {session.agent} session",
        f"Title: {session.title}",
        f"Directory: {session.directory or '(unknown)'}",
        f"Turns: {session.message_count}",
        "",
    ]
    if first:
        parts.append(f"Initial ask: {_truncate(first, 600)}")
    if last and last != first:
        parts.append(f"Most recent ask: {_truncate(last, 600)}")
    return "\n".join(parts).strip() + "\n"


def _hybrid(session: Session) -> str:
    summary = _summary(session)
    msgs = _split_messages(session.content)
    # Take last N turn-pairs. We approximate a "turn pair" as one user msg
    # + the assistant msgs that follow until the next user msg.
    if not msgs:
        return summary

    # find indices of user messages
    user_idxs = [i for i, m in enumerate(msgs) if m.startswith("» ")]
    if len(user_idxs) <= HYBRID_TURN_PAIRS:
        tail = msgs
    else:
        start = user_idxs[-HYBRID_TURN_PAIRS]
        tail = msgs[start:]

    return summary + "\n## Last turns of the conversation\n\n" + "\n\n".join(tail) + "\n"


def _full(session: Session) -> str:
    summary = _summary(session)
    body = summary + "\n## Full transcript\n\n" + session.content + "\n"
    # Hard cap to avoid pathological prompts.
    enc = _encoder()
    tokens = enc.encode(body)
    if len(tokens) <= MAX_FULL_TOKENS:
        return body
    truncated = enc.decode(tokens[:MAX_FULL_TOKENS])
    return truncated.rstrip() + "\n…\n[truncated to keep context within budget]\n"


# ---- public -----------------------------------------------------------------


def compact(session: Session, strategy: Strategy) -> ContextBundle:
    if strategy == "summary":
        text = _summary(session)
    elif strategy == "hybrid":
        text = _hybrid(session)
    elif strategy == "full":
        text = _full(session)
    else:
        raise ValueError(f"Unknown strategy: {strategy}")
    return ContextBundle(
        text=text,
        token_count=_count_tokens(text),
        strategy=strategy,
        source_session_id=session.id,
        source_agent=session.agent,
    )


def estimate_tokens(text: str) -> int:
    """Convenience for the modal to show a live estimate."""
    return _count_tokens(text)
