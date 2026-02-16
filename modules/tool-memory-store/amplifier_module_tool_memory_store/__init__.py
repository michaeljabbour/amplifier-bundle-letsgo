"""Durable memory store with SQLite, FTS5, scored search, CRUD, dedup, and TTL.

Implements the full search_v2 contract: search_v2, search_ids, get, plus basic
CRUD operations as an Amplifier Tool.  Registers the ``memory.store``
capability so hooks-memory-inject auto-discovers it.

Hardening features:

* **Deduplication** — content-hash check before insert to prevent duplicates.
* **TTL / expiry** — optional ``expires_at`` column; expired memories are
  excluded from search and periodically purged by ``purge_expired()``.
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from amplifier_core.models import ToolResult  # type: ignore[import-not-found]

__amplifier_module_type__ = "tool"

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

_DEFAULT_TRUST = 0.5
_DEFAULT_SENSITIVITY = "public"

# ---------------------------------------------------------------------------
# Scoring helpers (mirrors hooks-memory-inject logic)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _ScoringConfig:
    w_match: float = 0.55
    w_recency: float = 0.20
    w_importance: float = 0.15
    w_trust: float = 0.10
    half_life_days: float = 21.0
    min_score: float = 0.35


def _parse_dt(value: Any) -> datetime | None:
    """Parse a datetime from str (ISO), int/float (timestamp), datetime, or None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (OSError, ValueError):
            return None
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _recency_score(updated_at: Any, half_life_days: float) -> float:
    """Exponential decay score based on age."""
    dt = _parse_dt(updated_at)
    if dt is None:
        return 0.2
    now = datetime.now(tz=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (now - dt).total_seconds() / 86400)
    return 0.5 ** (age_days / half_life_days)


def _compute_score(
    item: dict[str, Any], *, match_score: float, cfg: _ScoringConfig
) -> float:
    """Weighted sum of match + recency + importance + trust."""
    recency = _recency_score(item.get("updated_at"), cfg.half_life_days)
    importance = float(item.get("importance", 0.5))
    trust = float(item.get("trust", _DEFAULT_TRUST))
    return (
        cfg.w_match * match_score
        + cfg.w_recency * recency
        + cfg.w_importance * importance
        + cfg.w_trust * trust
    )


def _extract_keywords(text: str, max_keywords: int = 8) -> list[str]:
    """Extract top keywords from text, filtering stopwords and short tokens."""
    words = text.lower().split()
    keywords = [w.strip(".,!?;:'\"()[]{}") for w in words]
    keywords = [w for w in keywords if len(w) > 2 and w not in _STOPWORDS]
    seen: set[str] = set()
    unique: list[str] = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique.append(kw)
    return unique[:max_keywords]


def _allow_by_sensitivity(
    sensitivity: str, *, allow_private: bool, allow_secret: bool
) -> bool:
    """Gate memory by its sensitivity level."""
    sensitivity = (sensitivity or _DEFAULT_SENSITIVITY).lower()
    if sensitivity == "public":
        return True
    if sensitivity == "private":
        return allow_private
    if sensitivity == "secret":
        return allow_secret
    return True  # unknown levels default to allowed


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL DEFAULT '',
    category TEXT DEFAULT 'general',
    importance REAL DEFAULT 0.5,
    trust REAL DEFAULT 0.5,
    sensitivity TEXT DEFAULT 'public',
    tags TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    expires_at TEXT DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_memories_content_hash ON memories(content_hash);
CREATE INDEX IF NOT EXISTS idx_memories_expires_at ON memories(expires_at);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
USING fts5(content, content='memories', content_rowid='rowid');

CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, content) VALUES (new.rowid, new.content);
END;

CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content)
        VALUES('delete', old.rowid, old.content);
END;

CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content)
        VALUES('delete', old.rowid, old.content);
    INSERT INTO memories_fts(rowid, content) VALUES (new.rowid, new.content);
END;
"""

# Migration: add columns if upgrading from older schema
_MIGRATIONS_SQL = [
    "ALTER TABLE memories ADD COLUMN content_hash TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE memories ADD COLUMN expires_at TEXT DEFAULT NULL",
]


# ---------------------------------------------------------------------------
# MemoryStore — the storage engine (registered as capability)
# ---------------------------------------------------------------------------


class MemoryStore:
    """SQLite-backed memory store with FTS5 search.

    Registered as the ``memory.store`` capability so hooks-memory-inject
    can call ``search_v2`` directly.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._write_lock = threading.Lock()
        self._init_db()

    # -- init ---------------------------------------------------------------

    def _init_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path))
        try:
            conn.executescript(_SCHEMA_SQL)
            # Apply migrations for existing databases
            for sql in _MIGRATIONS_SQL:
                try:
                    conn.execute(sql)
                except sqlite3.OperationalError:
                    pass  # column already exists
            conn.commit()
        finally:
            conn.close()

    def _ro_connection(self) -> sqlite3.Connection:
        """Open a read-only connection."""
        conn = sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def _rw_connection(self) -> sqlite3.Connection:
        """Open a read-write connection."""
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    # -- CRUD ---------------------------------------------------------------

    @staticmethod
    def _content_hash(content: str) -> str:
        """SHA-256 hex digest of *content* for deduplication."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def store(
        self,
        content: str,
        category: str = "general",
        importance: float = 0.5,
        trust: float = 0.5,
        sensitivity: str = "public",
        tags: list[str] | str | None = None,
        ttl_days: float | None = None,
    ) -> str:
        """Store a new memory. Returns the new id.

        **Deduplication**: if a memory with identical content already exists,
        its ``updated_at`` is refreshed and its id is returned instead of
        creating a duplicate.

        **TTL**: if *ttl_days* is provided, ``expires_at`` is set.  Expired
        memories are excluded from search and purged by ``purge_expired()``.
        """
        chash = self._content_hash(content)
        mem_id = uuid.uuid4().hex[:12]
        now = datetime.now(tz=timezone.utc).isoformat()
        tag_str = ",".join(tags) if isinstance(tags, list) else (tags or "")

        expires_at: str | None = None
        if ttl_days is not None and ttl_days > 0:
            from datetime import timedelta

            expires_at = (
                datetime.now(tz=timezone.utc) + timedelta(days=ttl_days)
            ).isoformat()

        with self._write_lock:
            conn = self._rw_connection()
            try:
                # Dedup check
                existing = conn.execute(
                    "SELECT id FROM memories WHERE content_hash = ?", (chash,)
                ).fetchone()
                if existing:
                    # Refresh the existing memory's timestamp
                    conn.execute(
                        "UPDATE memories SET updated_at = ? WHERE id = ?",
                        (now, existing["id"]),
                    )
                    conn.commit()
                    logger.debug("Dedup hit: refreshed memory %s", existing["id"])
                    return existing["id"]

                conn.execute(
                    "INSERT INTO memories (id, content, content_hash, category, "
                    "importance, trust, sensitivity, tags, created_at, updated_at, "
                    "expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        mem_id,
                        content,
                        chash,
                        category,
                        importance,
                        trust,
                        sensitivity,
                        tag_str,
                        now,
                        now,
                        expires_at,
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        return mem_id

    def purge_expired(self) -> int:
        """Delete all memories whose ``expires_at`` has passed.  Returns count."""
        now = datetime.now(tz=timezone.utc).isoformat()
        with self._write_lock:
            conn = self._rw_connection()
            try:
                cursor = conn.execute(
                    "DELETE FROM memories WHERE expires_at IS NOT NULL "
                    "AND expires_at < ?",
                    (now,),
                )
                conn.commit()
                deleted = cursor.rowcount
            finally:
                conn.close()
        if deleted:
            logger.info("Purged %d expired memories", deleted)
        return deleted

    def get(self, ids: Sequence[str]) -> list[dict[str, Any]]:
        """Get memories by id(s)."""
        if not ids:
            return []
        conn = self._ro_connection()
        try:
            placeholders = ",".join("?" for _ in ids)
            cursor = conn.execute(
                f"SELECT * FROM memories WHERE id IN ({placeholders})",  # noqa: S608
                list(ids),
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def delete(self, id: str) -> bool:
        """Delete a memory by id. Returns True if deleted."""
        with self._write_lock:
            conn = self._rw_connection()
            try:
                cursor = conn.execute("DELETE FROM memories WHERE id = ?", (id,))
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    def list_all(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """List memory metadata (no full content for large lists)."""
        conn = self._ro_connection()
        try:
            cursor = conn.execute(
                "SELECT id, category, importance, trust, sensitivity, tags, "
                "created_at, updated_at, "
                "SUBSTR(content, 1, 100) AS content_preview "
                "FROM memories ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def count(self) -> int:
        """Return total number of memories."""
        conn = self._ro_connection()
        try:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM memories").fetchone()
            return row["cnt"] if row else 0
        finally:
            conn.close()

    # -- search (scored contract) --------------------------------------------

    def _search_fts(self, query: str, limit: int) -> list[tuple[dict[str, Any], float]]:
        """Search via FTS5 with bm25 scoring.  Excludes expired memories."""
        conn = self._ro_connection()
        now = datetime.now(tz=timezone.utc).isoformat()
        try:
            cursor = conn.execute(
                "SELECT m.*, bm25(memories_fts) AS _bm25 "
                "FROM memories_fts f "
                "JOIN memories m ON m.rowid = f.rowid "
                "WHERE memories_fts MATCH ? "
                "AND (m.expires_at IS NULL OR m.expires_at > ?) "
                "ORDER BY rank LIMIT ?",
                (query, now, limit),
            )
            results: list[tuple[dict[str, Any], float]] = []
            for row in cursor.fetchall():
                d = dict(row)
                bm25_score = d.pop("_bm25", 0.0)
                match_score = 1.0 / (1.0 + max(0.0, bm25_score))
                results.append((d, match_score))
            return results
        finally:
            conn.close()

    def _search_like(
        self, keywords: list[str], limit: int
    ) -> list[tuple[dict[str, Any], float]]:
        """Fallback: LIKE search with keyword hit counting.  Excludes expired."""
        if not keywords:
            return []
        conn = self._ro_connection()
        now = datetime.now(tz=timezone.utc).isoformat()
        try:
            conditions = " OR ".join(["content LIKE ?"] * len(keywords))
            params: list[Any] = [f"%{kw}%" for kw in keywords]
            params.extend([now, limit])
            cursor = conn.execute(
                f"SELECT * FROM memories WHERE ({conditions}) "  # noqa: S608
                "AND (expires_at IS NULL OR expires_at > ?) "
                "ORDER BY updated_at DESC LIMIT ?",
                params,
            )
            results: list[tuple[dict[str, Any], float]] = []
            for row in cursor.fetchall():
                d = dict(row)
                content_lower = d.get("content", "").lower()
                hits = sum(1 for kw in keywords if kw in content_lower)
                match_score = min(0.75, 0.15 + 0.15 * hits)
                results.append((d, match_score))
            return results
        finally:
            conn.close()

    def _search_raw(
        self, prompt: str, *, candidate_limit: int
    ) -> list[tuple[dict[str, Any], float]]:
        """Run search: try FTS5, fall back to LIKE."""
        keywords = _extract_keywords(prompt)
        if not keywords:
            return []
        fts_query = " OR ".join(keywords)
        try:
            return self._search_fts(fts_query, candidate_limit)
        except sqlite3.OperationalError:
            logger.debug("FTS5 not available, falling back to LIKE search")
            return self._search_like(keywords, candidate_limit)

    def _rerank_and_filter(
        self,
        items: list[tuple[dict[str, Any], float]],
        *,
        cfg: _ScoringConfig,
        limit: int,
        allow_private: bool,
        allow_secret: bool,
    ) -> list[dict[str, Any]]:
        """Score, gate, filter, sort, truncate."""
        scored: list[tuple[dict[str, Any], float]] = []
        for item, match_score in items:
            sensitivity = item.get("sensitivity", _DEFAULT_SENSITIVITY)
            if not _allow_by_sensitivity(
                sensitivity, allow_private=allow_private, allow_secret=allow_secret
            ):
                continue
            score = _compute_score(item, match_score=match_score, cfg=cfg)
            if score >= cfg.min_score:
                item["_score"] = round(score, 3)
                item["_match"] = round(match_score, 3)
                scored.append((item, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [item for item, _ in scored[:limit]]

    def search_v2(
        self,
        prompt: str,
        *,
        limit: int = 5,
        candidate_limit: int = 25,
        scoring: dict[str, Any] | None = None,
        gating: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Scored search with sensitivity gating."""
        s = scoring or {}
        g = gating or {}
        cfg = _ScoringConfig(
            w_match=float(s.get("w_match", 0.55)),
            w_recency=float(s.get("w_recency", 0.20)),
            w_importance=float(s.get("w_importance", 0.15)),
            w_trust=float(s.get("w_trust", 0.10)),
            half_life_days=float(s.get("half_life_days", 21.0)),
            min_score=float(s.get("min_score", 0.35)),
        )
        raw = self._search_raw(prompt, candidate_limit=candidate_limit)
        return self._rerank_and_filter(
            raw,
            cfg=cfg,
            limit=limit,
            allow_private=g.get("allow_private", False),
            allow_secret=g.get("allow_secret", False),
        )

    def search_ids(
        self,
        prompt: str,
        *,
        candidate_limit: int = 50,
        scoring: dict[str, Any] | None = None,
        gating: dict[str, Any] | None = None,
    ) -> list[str]:
        """Return matching memory ids."""
        results = self.search_v2(
            prompt,
            limit=candidate_limit,
            candidate_limit=candidate_limit,
            scoring=scoring,
            gating=gating,
        )
        return [r["id"] for r in results]


# ---------------------------------------------------------------------------
# MemoryTool — LLM-callable Amplifier Tool
# ---------------------------------------------------------------------------


class MemoryTool:
    """Amplifier Tool wrapping MemoryStore for LLM use."""

    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    @property
    def name(self) -> str:
        return "memory"

    @property
    def description(self) -> str:
        return (
            "Persistent memory store. Store, search, list, get, and delete "
            "memories across sessions."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["operation"],
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "store_memory",
                        "search_memories",
                        "list_memories",
                        "get_memory",
                        "delete_memory",
                        "purge_expired",
                    ],
                    "description": "The operation to perform.",
                },
                "content": {
                    "type": "string",
                    "description": "Memory content (for store_memory).",
                },
                "category": {
                    "type": "string",
                    "description": "Category tag (for store_memory).",
                },
                "importance": {
                    "type": "number",
                    "description": "Importance 0-1 (for store_memory).",
                },
                "sensitivity": {
                    "type": "string",
                    "enum": ["public", "private", "secret"],
                    "description": "Sensitivity level (for store_memory).",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags (for store_memory).",
                },
                "query": {
                    "type": "string",
                    "description": "Search query (for search_memories).",
                },
                "id": {
                    "type": "string",
                    "description": "Memory id (for get_memory / delete_memory).",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (for search/list).",
                },
                "offset": {
                    "type": "integer",
                    "description": "Offset (for list_memories).",
                },
                "min_score": {
                    "type": "number",
                    "description": "Minimum score threshold (for search_memories).",
                },
                "ttl_days": {
                    "type": "number",
                    "description": (
                        "Time-to-live in days (for store_memory). "
                        "Memory expires and is excluded from search after this."
                    ),
                },
            },
        }

    async def execute(self, input: dict[str, Any]) -> ToolResult:  # noqa: A002
        """Execute a memory operation.  Returns ``ToolResult`` per protocol."""
        op = input.get("operation", "")

        try:
            if op == "store_memory":
                content = input.get("content", "")
                if not content:
                    return ToolResult(
                        success=False,
                        error={"message": "content is required for store_memory"},
                    )
                mem_id = self._store.store(
                    content=content,
                    category=input.get("category", "general"),
                    importance=float(input.get("importance", 0.5)),
                    sensitivity=input.get("sensitivity", "public"),
                    tags=input.get("tags"),
                    ttl_days=input.get("ttl_days"),
                )
                return ToolResult(
                    success=True, output={"id": mem_id, "status": "stored"}
                )

            if op == "search_memories":
                query = input.get("query", "")
                if not query:
                    return ToolResult(
                        success=False,
                        error={"message": "query is required for search_memories"},
                    )
                limit = int(input.get("limit", 10))
                min_score = float(input.get("min_score", 0.0))
                scoring = {"min_score": min_score} if min_score else None
                results = self._store.search_v2(query, limit=limit, scoring=scoring)
                return ToolResult(
                    success=True,
                    output={"results": results, "count": len(results)},
                )

            if op == "list_memories":
                limit = int(input.get("limit", 100))
                offset = int(input.get("offset", 0))
                memories = self._store.list_all(limit=limit, offset=offset)
                total = self._store.count()
                return ToolResult(
                    success=True, output={"memories": memories, "total": total}
                )

            if op == "get_memory":
                mem_id = input.get("id", "")
                if not mem_id:
                    return ToolResult(
                        success=False,
                        error={"message": "id is required for get_memory"},
                    )
                records = self._store.get([mem_id])
                if not records:
                    return ToolResult(
                        success=False,
                        error={"message": f"memory {mem_id} not found"},
                    )
                return ToolResult(success=True, output=records[0])

            if op == "delete_memory":
                mem_id = input.get("id", "")
                if not mem_id:
                    return ToolResult(
                        success=False,
                        error={"message": "id is required for delete_memory"},
                    )
                deleted = self._store.delete(mem_id)
                return ToolResult(success=True, output={"deleted": deleted})

            if op == "purge_expired":
                count = self._store.purge_expired()
                return ToolResult(
                    success=True, output={"purged": count}
                )

            return ToolResult(
                success=False,
                error={"message": f"unknown operation: {op}"},
            )
        except Exception:
            logger.exception("Unexpected error in memory tool")
            return ToolResult(
                success=False,
                error={"message": "An internal error occurred. Check logs."},
            )


# ---------------------------------------------------------------------------
# Module entry point
# ---------------------------------------------------------------------------


async def mount(coordinator: Any, config: dict[str, Any] | None = None) -> None:
    """Mount tool-memory-store: register as Tool and as memory.store capability."""
    cfg = config or {}
    db_path = Path(cfg.get("db_path", "~/.letsgo/memories.db")).expanduser()

    store = MemoryStore(db_path)
    tool = MemoryTool(store)

    # Register as Tool (LLM-callable)
    await coordinator.mount("tools", tool, name="tool-memory-store")

    # Register as capability (so hooks-memory-inject auto-discovers it)
    coordinator.register_capability("memory.store", store)

    logger.info("tool-memory-store mounted (db: %s)", db_path)
