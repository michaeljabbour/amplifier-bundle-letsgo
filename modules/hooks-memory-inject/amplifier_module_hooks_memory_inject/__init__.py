"""Auto-inject relevant memories into agent context at prompt time.

Queries the memory store (or a local SQLite database) for memories relevant
to the current prompt and injects them as ephemeral context so the agent
can leverage past knowledge without explicit recall.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

from amplifier_core.models import HookResult

__amplifier_module_type__ = "hook"

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stopwords for keyword extraction
# ---------------------------------------------------------------------------

_STOPWORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "have",
        "how",
        "i",
        "in",
        "is",
        "it",
        "its",
        "me",
        "my",
        "not",
        "of",
        "on",
        "or",
        "so",
        "that",
        "the",
        "this",
        "to",
        "was",
        "we",
        "what",
        "when",
        "who",
        "will",
        "with",
        "you",
        "your",
    }
)


# ---------------------------------------------------------------------------
# Memory retrieval
# ---------------------------------------------------------------------------


def _extract_keywords(text: str, max_keywords: int = 5) -> list[str]:
    """Extract top keywords from text, filtering stopwords and short tokens."""
    words = text.lower().split()
    keywords = [w.strip(".,!?;:'\"()[]{}") for w in words]
    keywords = [w for w in keywords if len(w) > 2 and w not in _STOPWORDS]  # noqa: PLR2004
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique.append(kw)
    return unique[:max_keywords]


def _search_sqlite_fts(
    db_path: Path, query: str, limit: int
) -> list[dict[str, Any]]:
    """Search memories using FTS5 full-text search."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(
            "SELECT * FROM memories_fts WHERE memories_fts MATCH ? "
            "ORDER BY rank LIMIT ?",
            (query, limit),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def _search_sqlite_like(
    db_path: Path, keywords: list[str], limit: int
) -> list[dict[str, Any]]:
    """Fallback search using LIKE on each keyword."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        if not keywords:
            return []
        # Build OR conditions for each keyword
        conditions = " OR ".join(["content LIKE ?"] * len(keywords))
        params: list[Any] = [f"%{kw}%" for kw in keywords]
        params.append(limit)
        cursor = conn.execute(
            f"SELECT * FROM memories WHERE ({conditions}) "  # noqa: S608
            "ORDER BY updated_at DESC LIMIT ?",
            params,
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def _search_sqlite(
    db_path: Path, prompt: str, limit: int
) -> list[dict[str, Any]]:
    """Search SQLite DB: try FTS5, fall back to LIKE."""
    keywords = _extract_keywords(prompt)
    if not keywords:
        return []

    fts_query = " OR ".join(keywords)

    try:
        return _search_sqlite_fts(db_path, fts_query, limit)
    except sqlite3.OperationalError:
        logger.debug("FTS5 not available, falling back to LIKE search")
        return _search_sqlite_like(db_path, keywords, limit)


# ---------------------------------------------------------------------------
# Context formatting
# ---------------------------------------------------------------------------


def _format_memory_context(
    memories: list[dict[str, Any]], max_tokens: int
) -> str:
    """Format memories into a context injection block.

    Approximates token count as words / 0.75 and truncates once the
    budget is exhausted.
    """
    lines: list[str] = [
        "<memory-context>",
        "Relevant memories (auto-retrieved):",
        "",
    ]
    approx_tokens = 10  # header overhead

    for idx, mem in enumerate(memories, 1):
        category = mem.get("category", "general")
        content = mem.get("content", "")
        importance = mem.get("importance", 0.5)
        updated_at = mem.get("updated_at", "unknown")

        # Truncate content preview to keep injection compact
        preview = content[:200] + ("..." if len(content) > 200 else "")

        line = (
            f"{idx}. [{category}] {preview} "
            f"(importance: {importance}, from: {updated_at})"
        )
        line_tokens = len(line.split()) / 0.75
        if approx_tokens + line_tokens > max_tokens:
            break
        lines.append(line)
        approx_tokens += line_tokens

    lines.append("")
    lines.append(
        "These memories were retrieved based on relevance to the current prompt."
    )
    lines.append(
        "Use them as context if helpful, but do not mention them unless relevant."
    )
    lines.append("</memory-context>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Hook handler
# ---------------------------------------------------------------------------


class MemoryInjector:
    """Queries memories and injects them as ephemeral context on each prompt."""

    def __init__(
        self,
        coordinator: Any,
        *,
        memory_db_path: Path,
        max_memories: int = 5,
        max_injection_tokens: int = 2000,
        min_relevance: float = 0.1,
        enabled: bool = True,
    ) -> None:
        self._coordinator = coordinator
        self._memory_db_path = memory_db_path
        self._max_memories = max_memories
        self._max_injection_tokens = max_injection_tokens
        self._min_relevance = min_relevance
        self._enabled = enabled

    async def on_prompt_submit(
        self, event: str, data: dict[str, Any]
    ) -> HookResult:
        """Handle prompt:submit -- retrieve and inject relevant memories."""
        if not self._enabled:
            return HookResult(action="continue")

        prompt = data.get("prompt", "")
        if not prompt or not prompt.strip():
            return HookResult(action="continue")

        memories = self._retrieve_memories(prompt)
        if not memories:
            return HookResult(action="continue")

        context = _format_memory_context(memories, self._max_injection_tokens)
        return HookResult(
            action="inject_context",
            context_injection=context,
            ephemeral=True,
        )

    def _retrieve_memories(self, prompt: str) -> list[dict[str, Any]]:
        """Try capability store first, then fall back to local SQLite."""
        # Strategy 1: memory.store capability (registered by tool-memory)
        try:
            store = self._coordinator.get_capability("memory.store")
            if store is not None:
                results = store.search(prompt, limit=self._max_memories)
                if results:
                    return [
                        r
                        for r in results
                        if r.get("importance", 1.0) >= self._min_relevance
                    ]
        except Exception:
            logger.debug(
                "memory.store capability unavailable or errored",
                exc_info=True,
            )

        # Strategy 2: local SQLite database
        if self._memory_db_path.exists():
            try:
                return _search_sqlite(
                    self._memory_db_path, prompt, self._max_memories
                )
            except Exception:
                logger.debug(
                    "SQLite memory search failed for %s",
                    self._memory_db_path,
                    exc_info=True,
                )

        return []


# ---------------------------------------------------------------------------
# Module entry point
# ---------------------------------------------------------------------------


async def mount(coordinator: Any, config: dict[str, Any] | None = None) -> None:
    """Mount memory-inject hook.

    Register a prompt:submit handler that injects relevant memories.
    """
    cfg = config or {}

    raw_path = cfg.get("memory_db_path", "~/.letsgo/memories.db")
    memory_db_path = Path(raw_path).expanduser()

    injector = MemoryInjector(
        coordinator,
        memory_db_path=memory_db_path,
        max_memories=int(cfg.get("max_memories", 5)),
        max_injection_tokens=int(cfg.get("max_injection_tokens", 2000)),
        min_relevance=float(cfg.get("min_relevance", 0.1)),
        enabled=bool(cfg.get("enabled", True)),
    )

    coordinator.hooks.register(
        event="prompt:submit",
        handler=injector.on_prompt_submit,
        priority=50,
        name="memory-inject.on_prompt_submit",
    )

    logger.info(
        "hooks-memory-inject mounted -- db=%s, max=%d",
        memory_db_path,
        injector._max_memories,
    )
