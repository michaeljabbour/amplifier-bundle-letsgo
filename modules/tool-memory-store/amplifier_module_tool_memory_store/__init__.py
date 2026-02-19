"""Durable memory store with SQLite, FTS5, scored search, CRUD, dedup, TTL,
structured fact store, memory summarization, rich observation metadata,
file tracking, concept tagging, and access-based eviction.

Implements the full search_v2 contract: search_v2, search_ids, get, plus basic
CRUD operations as an Amplifier Tool.  Registers the ``memory.store``
capability so hooks-memory-inject auto-discovers it.

Hardening features:

* **Deduplication** — content-hash check before insert to prevent duplicates.
* **TTL / expiry** — optional ``expires_at`` column; expired memories are
  excluded from search and periodically purged by ``purge_expired()``.
* **Fact store** — subject/predicate/object triples with confidence scoring.
* **Summarization** — automatic condensation of old memories into summaries.
* **Rich metadata** — observation type, title, subtitle, concepts, file tracking.
* **Access counting** — tracks how often each memory is retrieved.
* **Max memories cap** — configurable limit with smart eviction.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

from amplifier_core.models import ToolResult  # type: ignore[import-not-found]

__amplifier_module_type__ = "tool"

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OBSERVATION_TYPES: list[str] = [
    "bugfix", "feature", "refactor", "change", "discovery", "decision",
    "session_summary", "compressed_summary",
]

CONCEPT_TYPES: list[str] = [
    "how-it-works", "why-it-exists", "what-changed",
    "problem-solution", "gotcha", "pattern", "trade-off",
]

# ---------------------------------------------------------------------------
# Stopwords for keyword extraction
# ---------------------------------------------------------------------------

_STOPWORDS: frozenset[str] = frozenset(
    {
        "a",
        "all",
        "also",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "but",
        "by",
        "can",
        "each",
        "for",
        "from",
        "has",
        "have",
        "how",
        "i",
        "in",
        "into",
        "is",
        "it",
        "its",
        "just",
        "me",
        "more",
        "my",
        "not",
        "of",
        "on",
        "one",
        "or",
        "our",
        "out",
        "so",
        "some",
        "than",
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

STOPWORDS: frozenset = _STOPWORDS  # Public alias for consumers

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
    return False  # unknown levels are denied (fail-closed)


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
    expires_at TEXT DEFAULT NULL,
    title TEXT DEFAULT '',
    subtitle TEXT DEFAULT '',
    type TEXT DEFAULT 'change',
    concepts TEXT DEFAULT '[]',
    files_read TEXT DEFAULT '[]',
    files_modified TEXT DEFAULT '[]',
    session_id TEXT DEFAULT NULL,
    project TEXT DEFAULT NULL,
    accessed_count INTEGER DEFAULT 0,
    discovery_tokens INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_memories_content_hash ON memories(content_hash);
CREATE INDEX IF NOT EXISTS idx_memories_expires_at ON memories(expires_at);
CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(type);
CREATE INDEX IF NOT EXISTS idx_memories_session_id ON memories(session_id);
CREATE INDEX IF NOT EXISTS idx_memories_project ON memories(project);
CREATE INDEX IF NOT EXISTS idx_memories_accessed ON memories(accessed_count);

CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS facts (
    id TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    source_entry_id TEXT DEFAULT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (source_entry_id) REFERENCES memories(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_facts_subject ON facts(subject);
CREATE INDEX IF NOT EXISTS idx_facts_predicate ON facts(predicate);

CREATE TABLE IF NOT EXISTS memory_journal (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    detail TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_journal_memory_id ON memory_journal(memory_id);
CREATE INDEX IF NOT EXISTS idx_journal_timestamp ON memory_journal(timestamp);
"""

# Migration: add columns if upgrading from older schema
_MIGRATIONS_SQL = [
    "ALTER TABLE memories ADD COLUMN content_hash TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE memories ADD COLUMN expires_at TEXT DEFAULT NULL",
    "ALTER TABLE memories ADD COLUMN title TEXT DEFAULT ''",
    "ALTER TABLE memories ADD COLUMN subtitle TEXT DEFAULT ''",
    "ALTER TABLE memories ADD COLUMN type TEXT DEFAULT 'change'",
    "ALTER TABLE memories ADD COLUMN concepts TEXT DEFAULT '[]'",
    "ALTER TABLE memories ADD COLUMN files_read TEXT DEFAULT '[]'",
    "ALTER TABLE memories ADD COLUMN files_modified TEXT DEFAULT '[]'",
    "ALTER TABLE memories ADD COLUMN session_id TEXT DEFAULT NULL",
    "ALTER TABLE memories ADD COLUMN project TEXT DEFAULT NULL",
    "ALTER TABLE memories ADD COLUMN accessed_count INTEGER DEFAULT 0",
    "ALTER TABLE memories ADD COLUMN discovery_tokens INTEGER DEFAULT 0",
]

# Current FTS version -- bump when FTS column set changes
_FTS_VERSION = "2"


# ---------------------------------------------------------------------------
# MemoryStore -- the storage engine (registered as capability)
# ---------------------------------------------------------------------------


class MemoryStore:
    """SQLite-backed memory store with FTS5 search, fact store, and
    summarization.

    Registered as the ``memory.store`` capability so hooks-memory-inject
    can call ``search_v2`` directly.
    """

    def __init__(self, db_path: Path, *, max_memories: int = 0) -> None:
        self._db_path = db_path
        self._max_memories = max_memories  # 0 = no limit
        self._write_lock = threading.Lock()
        self._init_db()

    # -- init ---------------------------------------------------------------

    def _init_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path))
        try:
            conn.executescript(_SCHEMA_SQL)
            # Apply column migrations for existing databases
            for sql in _MIGRATIONS_SQL:
                try:
                    conn.execute(sql)
                except sqlite3.OperationalError:
                    pass  # column already exists
            conn.commit()
        finally:
            conn.close()
        # Create or upgrade FTS index (separate step -- needs columns first)
        self._ensure_fts()

    def _ensure_fts(self) -> None:
        """Create or upgrade the FTS5 index to cover content, title, subtitle."""
        conn = sqlite3.connect(str(self._db_path))
        try:
            # Check current FTS version
            try:
                row = conn.execute(
                    "SELECT value FROM schema_meta WHERE key = 'fts_version'"
                ).fetchone()
                current_version = row[0] if row else "0"
            except sqlite3.OperationalError:
                current_version = "0"

            if current_version == _FTS_VERSION:
                return  # Already up to date

            logger.info(
                "Upgrading FTS index from version %s to %s",
                current_version,
                _FTS_VERSION,
            )

            # Drop old triggers and FTS table
            conn.execute("DROP TRIGGER IF EXISTS memories_ai")
            conn.execute("DROP TRIGGER IF EXISTS memories_ad")
            conn.execute("DROP TRIGGER IF EXISTS memories_au")
            conn.execute("DROP TABLE IF EXISTS memories_fts")

            # Create 3-column FTS5 table
            conn.execute(
                "CREATE VIRTUAL TABLE memories_fts "
                "USING fts5(content, title, subtitle, "
                "content='memories', content_rowid='rowid')"
            )

            # Create sync triggers
            conn.execute(
                "CREATE TRIGGER memories_ai AFTER INSERT ON memories BEGIN "
                "INSERT INTO memories_fts(rowid, content, title, subtitle) "
                "VALUES (new.rowid, new.content, new.title, new.subtitle); "
                "END"
            )
            conn.execute(
                "CREATE TRIGGER memories_ad AFTER DELETE ON memories BEGIN "
                "INSERT INTO memories_fts(memories_fts, rowid, content, title, subtitle) "
                "VALUES('delete', old.rowid, old.content, old.title, old.subtitle); "
                "END"
            )
            conn.execute(
                "CREATE TRIGGER memories_au AFTER UPDATE ON memories BEGIN "
                "INSERT INTO memories_fts(memories_fts, rowid, content, title, subtitle) "
                "VALUES('delete', old.rowid, old.content, old.title, old.subtitle); "
                "INSERT INTO memories_fts(rowid, content, title, subtitle) "
                "VALUES (new.rowid, new.content, new.title, new.subtitle); "
                "END"
            )

            # Populate FTS from existing data
            conn.execute(
                "INSERT INTO memories_fts(rowid, content, title, subtitle) "
                "SELECT rowid, content, "
                "COALESCE(title, ''), COALESCE(subtitle, '') "
                "FROM memories"
            )

            # Record the version
            conn.execute(
                "INSERT OR REPLACE INTO schema_meta (key, value) "
                "VALUES ('fts_version', ?)",
                (_FTS_VERSION,),
            )
            conn.commit()
            logger.info("FTS5 index upgraded to version %s", _FTS_VERSION)
        except Exception:
            logger.exception("Failed to upgrade FTS index")
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

    # -- journal ------------------------------------------------------------

    def _journal(
        self, conn: sqlite3.Connection, memory_id: str, operation: str, detail: str = ""
    ) -> None:
        """Append an entry to the append-only ``memory_journal`` table.

        Called inside an existing write transaction so no extra locking is
        needed.  Failures are logged but never raised -- the journal must not
        break primary operations.
        """
        try:
            now = datetime.now(tz=timezone.utc).isoformat()
            conn.execute(
                "INSERT INTO memory_journal (memory_id, operation, timestamp, detail) "
                "VALUES (?, ?, ?, ?)",
                (memory_id, operation, now, detail[:500]),
            )
        except Exception:
            logger.debug("journal write failed for %s/%s", operation, memory_id, exc_info=True)

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
        *,
        title: str = "",
        subtitle: str = "",
        type: str = "change",
        concepts: list[str] | None = None,
        files_read: list[str] | None = None,
        files_modified: list[str] | None = None,
        session_id: str | None = None,
        project: str | None = None,
        discovery_tokens: int = 0,
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
            expires_at = (
                datetime.now(tz=timezone.utc) + timedelta(days=ttl_days)
            ).isoformat()

        # Validate observation type
        if type not in OBSERVATION_TYPES:
            type = "change"

        # Auto-generate title if not provided
        if not title and content:
            title = content[:80] + ("..." if len(content) > 80 else "")

        concepts_json = json.dumps(concepts or [])
        files_read_json = json.dumps(files_read or [])
        files_modified_json = json.dumps(files_modified or [])

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
                    self._journal(conn, existing["id"], "dedup_refresh")
                    conn.commit()
                    logger.debug("Dedup hit: refreshed memory %s", existing["id"])
                    return existing["id"]

                conn.execute(
                    "INSERT INTO memories (id, content, content_hash, category, "
                    "importance, trust, sensitivity, tags, created_at, updated_at, "
                    "expires_at, title, subtitle, type, concepts, files_read, "
                    "files_modified, session_id, project, accessed_count, "
                    "discovery_tokens) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                        title,
                        subtitle,
                        type,
                        concepts_json,
                        files_read_json,
                        files_modified_json,
                        session_id,
                        project,
                        0,
                        discovery_tokens,
                    ),
                )
                self._journal(
                    conn, mem_id, "insert",
                    f"category={category} type={type} sensitivity={sensitivity}",
                )
                conn.commit()
            finally:
                conn.close()

        # Enforce max_memories limit
        self._enforce_limit()

        return mem_id

    def update(
        self,
        id: str,
        *,
        content: str | None = None,
        title: str | None = None,
        subtitle: str | None = None,
        type: str | None = None,
        concepts: list[str] | None = None,
        files_read: list[str] | None = None,
        files_modified: list[str] | None = None,
        category: str | None = None,
        importance: float | None = None,
        tags: list[str] | None = None,
        sensitivity: str | None = None,
        trust: float | None = None,
    ) -> dict[str, Any] | None:
        """Update a memory in place.  Returns the updated dict, or None."""
        now = datetime.now(tz=timezone.utc).isoformat()
        updates: list[str] = ["updated_at = ?"]
        params: list[Any] = [now]

        if content is not None:
            updates.append("content = ?")
            params.append(content)
            updates.append("content_hash = ?")
            params.append(self._content_hash(content))
        if title is not None:
            updates.append("title = ?")
            params.append(title)
        if subtitle is not None:
            updates.append("subtitle = ?")
            params.append(subtitle)
        if type is not None and type in OBSERVATION_TYPES:
            updates.append("type = ?")
            params.append(type)
        if concepts is not None:
            updates.append("concepts = ?")
            params.append(json.dumps(concepts))
        if files_read is not None:
            updates.append("files_read = ?")
            params.append(json.dumps(files_read))
        if files_modified is not None:
            updates.append("files_modified = ?")
            params.append(json.dumps(files_modified))
        if category is not None:
            updates.append("category = ?")
            params.append(category)
        if importance is not None:
            updates.append("importance = ?")
            params.append(max(0.0, min(1.0, importance)))
        if tags is not None:
            updates.append("tags = ?")
            params.append(",".join(tags) if isinstance(tags, list) else tags)
        if sensitivity is not None:
            updates.append("sensitivity = ?")
            params.append(sensitivity)
        if trust is not None:
            updates.append("trust = ?")
            params.append(max(0.0, min(1.0, trust)))

        params.append(id)
        query = f"UPDATE memories SET {', '.join(updates)} WHERE id = ?"  # noqa: S608

        with self._write_lock:
            conn = self._rw_connection()
            try:
                cursor = conn.execute(query, params)
                if cursor.rowcount == 0:
                    return None
                self._journal(conn, id, "update")
                conn.commit()
            finally:
                conn.close()

        # Return the updated memory
        records = self.get([id])
        return records[0] if records else None

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

    def get(self, ids: Sequence[str], *, _increment_access: bool = False) -> list[dict[str, Any]]:
        """Get memories by id(s).  Optionally increment access count."""
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        id_list = list(ids)

        if _increment_access:
            with self._write_lock:
                conn = self._rw_connection()
                try:
                    conn.execute(
                        "UPDATE memories SET accessed_count = accessed_count + 1 "
                        f"WHERE id IN ({placeholders})",  # noqa: S608
                        id_list,
                    )
                    conn.commit()
                    cursor = conn.execute(
                        f"SELECT * FROM memories WHERE id IN ({placeholders})",  # noqa: S608
                        id_list,
                    )
                    return [dict(row) for row in cursor.fetchall()]
                finally:
                    conn.close()

        conn = self._ro_connection()
        try:
            cursor = conn.execute(
                f"SELECT * FROM memories WHERE id IN ({placeholders})",  # noqa: S608
                id_list,
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
                if cursor.rowcount > 0:
                    self._journal(conn, id, "delete")
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    def list_all(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """List memory metadata (no full content for large lists)."""
        conn = self._ro_connection()
        try:
            cursor = conn.execute(
                "SELECT id, title, subtitle, type, category, importance, trust, "
                "sensitivity, tags, concepts, session_id, project, "
                "accessed_count, discovery_tokens, created_at, updated_at, "
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
            # Search across content, title, and subtitle
            field_conditions: list[str] = []
            params: list[Any] = []
            for kw in keywords:
                field_conditions.append(
                    "(content LIKE ? OR title LIKE ? OR subtitle LIKE ?)"
                )
                params.extend([f"%{kw}%", f"%{kw}%", f"%{kw}%"])
            conditions = " OR ".join(field_conditions)
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
                searchable = (
                    (d.get("content") or "").lower()
                    + " " + (d.get("title") or "").lower()
                    + " " + (d.get("subtitle") or "").lower()
                )
                hits = sum(1 for kw in keywords if kw in searchable)
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
        results = self._rerank_and_filter(
            raw,
            cfg=cfg,
            limit=limit,
            allow_private=g.get("allow_private", False),
            allow_secret=g.get("allow_secret", False),
        )

        # Self-amplifying access tracking — boost retrieved memories
        result_ids = [m["id"] for m in results if "id" in m]
        if result_ids:
            self.get(result_ids, _increment_access=True)

        return results

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

    # -- New search operations -----------------------------------------------

    def search_by_file(self, file_path: str, *, limit: int = 10) -> list[dict[str, Any]]:
        """Search memories by file path (in files_read or files_modified)."""
        conn = self._ro_connection()
        try:
            pattern = f'%"{file_path}"%'
            cursor = conn.execute(
                "SELECT * FROM memories "
                "WHERE files_read LIKE ? OR files_modified LIKE ? "
                "ORDER BY updated_at DESC LIMIT ?",
                (pattern, pattern, limit),
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def search_by_concept(self, concept: str, *, limit: int = 10) -> list[dict[str, Any]]:
        """Search memories by concept tag."""
        conn = self._ro_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM memories "
                "WHERE concepts LIKE ? "
                "ORDER BY importance DESC, updated_at DESC LIMIT ?",
                (f'%"{concept}"%', limit),
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_timeline(
        self,
        *,
        limit: int = 50,
        type: str | None = None,
        project: str | None = None,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get memories ordered by creation date, optionally filtered."""
        conditions: list[str] = []
        params: list[Any] = []
        now = datetime.now(tz=timezone.utc).isoformat()

        conditions.append("(expires_at IS NULL OR expires_at > ?)")
        params.append(now)

        if type is not None:
            conditions.append("type = ?")
            params.append(type)
        if project is not None:
            conditions.append("project = ?")
            params.append(project)
        if session_id is not None:
            conditions.append("session_id = ?")
            params.append(session_id)

        where = " AND ".join(conditions)
        params.append(limit)

        conn = self._ro_connection()
        try:
            cursor = conn.execute(
                f"SELECT * FROM memories WHERE {where} "  # noqa: S608
                "ORDER BY created_at DESC LIMIT ?",
                params,
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    # -- Public scoring API (for hooks-memory-inject and other consumers) ---

    @staticmethod
    def extract_keywords(text: str, max_keywords: int = 8) -> list[str]:
        """Extract meaningful keywords from text, stripping stopwords."""
        return _extract_keywords(text, max_keywords=max_keywords)

    @staticmethod
    def compute_score(
        item: dict,
        *,
        match_score: float,
        weights: dict | None = None,
        half_life_days: float = 21.0,
    ) -> float:
        """Compute composite relevance score for a memory."""
        cfg = _ScoringConfig(
            w_match=weights.get("match", 0.55) if weights else 0.55,
            w_recency=weights.get("recency", 0.20) if weights else 0.20,
            w_importance=weights.get("importance", 0.15) if weights else 0.15,
            w_trust=weights.get("trust", 0.10) if weights else 0.10,
            half_life_days=half_life_days,
        )
        return _compute_score(item, match_score=match_score, cfg=cfg)

    @staticmethod
    def allow_by_sensitivity(
        sensitivity: str,
        *,
        allow_private: bool = False,
        allow_secret: bool = False,
    ) -> bool:
        """Check if a memory's sensitivity level allows access."""
        return _allow_by_sensitivity(
            sensitivity, allow_private=allow_private, allow_secret=allow_secret
        )

    # -- Max memories eviction -----------------------------------------------

    def _enforce_limit(self) -> None:
        """Remove least-accessed + oldest memories if over max_memories cap.

        Eviction priority: lowest accessed_count, then oldest updated_at,
        then lowest importance.
        """
        if self._max_memories <= 0:
            return
        with self._write_lock:
            conn = self._rw_connection()
            try:
                row = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM memories"
                ).fetchone()
                total = row["cnt"] if row else 0
                if total <= self._max_memories:
                    return
                to_remove = total - self._max_memories
                conn.execute(
                    "DELETE FROM memories WHERE id IN ("
                    "SELECT id FROM memories "
                    "ORDER BY accessed_count ASC, updated_at ASC, importance ASC "
                    f"LIMIT {to_remove})",
                )
                conn.commit()
                logger.info(
                    "Evicted %d memories to stay under max_memories=%d",
                    to_remove,
                    self._max_memories,
                )
            finally:
                conn.close()

    # -- Fact Store ----------------------------------------------------------

    def store_fact(
        self,
        subject: str,
        predicate: str,
        object_value: str,
        confidence: float = 1.0,
        source_entry_id: str | None = None,
    ) -> str:
        """Store a subject/predicate/object fact triple.  Returns the fact id.

        **Deduplication**: if an identical (subject, predicate, object) triple
        already exists, its ``confidence`` and ``updated_at`` are updated
        instead of creating a duplicate.
        """
        now = datetime.now(tz=timezone.utc).isoformat()
        fact_id = uuid.uuid4().hex[:12]

        with self._write_lock:
            conn = self._rw_connection()
            try:
                existing = conn.execute(
                    "SELECT id FROM facts "
                    "WHERE subject = ? AND predicate = ? AND object = ?",
                    (subject, predicate, object_value),
                ).fetchone()
                if existing:
                    conn.execute(
                        "UPDATE facts SET confidence = ?, updated_at = ? "
                        "WHERE id = ?",
                        (confidence, now, existing["id"]),
                    )
                    conn.commit()
                    logger.debug("Fact dedup hit: updated fact %s", existing["id"])
                    return existing["id"]

                conn.execute(
                    "INSERT INTO facts (id, subject, predicate, object, "
                    "confidence, source_entry_id, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        fact_id,
                        subject,
                        predicate,
                        object_value,
                        confidence,
                        source_entry_id,
                        now,
                        now,
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        return fact_id

    def query_facts(
        self,
        subject: str | None = None,
        predicate: str | None = None,
        object_value: str | None = None,
        min_confidence: float = 0.0,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Query facts by any combination of subject/predicate/object filters.

        Returns a list of fact dicts.
        """
        conditions: list[str] = ["confidence >= ?"]
        params: list[Any] = [min_confidence]

        if subject is not None:
            conditions.append("subject = ?")
            params.append(subject)
        if predicate is not None:
            conditions.append("predicate = ?")
            params.append(predicate)
        if object_value is not None:
            conditions.append("object = ?")
            params.append(object_value)

        where = " AND ".join(conditions)
        params.append(limit)

        conn = self._ro_connection()
        try:
            cursor = conn.execute(
                f"SELECT * FROM facts WHERE {where} "  # noqa: S608
                "ORDER BY updated_at DESC LIMIT ?",
                params,
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def delete_fact(self, fact_id: str) -> bool:
        """Delete a fact by id.  Returns True if deleted."""
        with self._write_lock:
            conn = self._rw_connection()
            try:
                cursor = conn.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    # -- Summarization -------------------------------------------------------

    def summarize_old(
        self,
        max_age_days: float = 30,
        max_memories: int = 5,
    ) -> dict[str, Any]:
        """Summarize old memories by category.

        For each category that has more than *max_memories* entries older than
        *max_age_days*, creates a single summary memory (concatenating first
        100 chars of each, joined by ``"; "``), stores it with
        ``category="{original}/summary"`` and ``importance=0.7``, then deletes
        the originals.

        Returns ``{"categories_summarized", "memories_archived",
        "summaries_created"}``.
        """
        cutoff = (
            datetime.now(tz=timezone.utc) - timedelta(days=max_age_days)
        ).isoformat()

        categories_summarized = 0
        memories_archived = 0
        summaries_created = 0

        # Read old memories grouped by category
        conn = self._ro_connection()
        try:
            rows = conn.execute(
                "SELECT id, content, category FROM memories "
                "WHERE updated_at < ? ORDER BY category, updated_at",
                (cutoff,),
            ).fetchall()
        finally:
            conn.close()

        # Group by category
        groups: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            d = dict(row)
            cat = d.get("category", "general")
            groups.setdefault(cat, []).append(d)

        # Summarize categories exceeding max_memories
        for category, entries in groups.items():
            if len(entries) <= max_memories:
                continue

            # Build summary content from previews
            previews = [entry["content"][:100] for entry in entries]
            summary_content = "; ".join(previews)

            # Store summary as a new memory
            self.store(
                content=summary_content,
                category=f"{category}/summary",
                importance=0.7,
            )
            summaries_created += 1

            # Delete the originals
            original_ids = [entry["id"] for entry in entries]
            with self._write_lock:
                conn = self._rw_connection()
                try:
                    placeholders = ",".join("?" for _ in original_ids)
                    conn.execute(
                        f"DELETE FROM memories WHERE id IN ({placeholders})",  # noqa: S608
                        original_ids,
                    )
                    conn.commit()
                finally:
                    conn.close()

            memories_archived += len(entries)
            categories_summarized += 1

        logger.info(
            "Summarized %d categories, archived %d memories, created %d summaries",
            categories_summarized,
            memories_archived,
            summaries_created,
        )
        return {
            "categories_summarized": categories_summarized,
            "memories_archived": memories_archived,
            "summaries_created": summaries_created,
        }


# ---------------------------------------------------------------------------
# MemoryTool -- LLM-callable Amplifier Tool
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
            "Persistent memory store with rich observation metadata, structured "
            "fact triples, file tracking, concept tagging, and summarization. "
            "Store, search, list, get, update, and delete memories across "
            "sessions. Search by file path or concept. Get timeline views. "
            "Store and query subject/predicate/object facts. "
            "Summarize old memories to keep the store compact."
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
                        "update_memory",
                        "delete_memory",
                        "search_by_file",
                        "search_by_concept",
                        "get_timeline",
                        "purge_expired",
                        "store_fact",
                        "query_facts",
                        "delete_fact",
                        "summarize_old",
                    ],
                    "description": "The operation to perform.",
                },
                "content": {
                    "type": "string",
                    "description": "Memory content (for store_memory, update_memory).",
                },
                "category": {
                    "type": "string",
                    "description": "Category tag (for store_memory, update_memory).",
                },
                "importance": {
                    "type": "number",
                    "description": "Importance 0-1 (for store_memory, update_memory).",
                },
                "sensitivity": {
                    "type": "string",
                    "enum": ["public", "private", "secret"],
                    "description": "Sensitivity level (for store_memory, update_memory).",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags (for store_memory, update_memory).",
                },
                "query": {
                    "type": "string",
                    "description": "Search query (for search_memories).",
                },
                "id": {
                    "type": "string",
                    "description": "Memory id (for get_memory / update_memory / delete_memory).",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (for search/list/query_facts/timeline).",
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
                # -- Rich metadata fields --
                "title": {
                    "type": "string",
                    "description": "Short title for the memory (for store_memory, update_memory).",
                },
                "subtitle": {
                    "type": "string",
                    "description": (
                        "Secondary description (for store_memory, update_memory)."
                    ),
                },
                "type": {
                    "type": "string",
                    "enum": OBSERVATION_TYPES,
                    "description": (
                        "Observation type (for store_memory, update_memory, get_timeline). "
                        "One of: bugfix, feature, refactor, change, discovery, decision."
                    ),
                },
                "concepts": {
                    "type": "array",
                    "items": {"type": "string", "enum": CONCEPT_TYPES},
                    "description": (
                        "Concept tags (for store_memory, update_memory). "
                        "Values: how-it-works, why-it-exists, what-changed, "
                        "problem-solution, gotcha, pattern, trade-off."
                    ),
                },
                "files_read": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "File paths read during this observation "
                        "(for store_memory, update_memory)."
                    ),
                },
                "files_modified": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "File paths modified (for store_memory, update_memory)."
                    ),
                },
                "session_id": {
                    "type": "string",
                    "description": (
                        "Session identifier (for store_memory, get_timeline)."
                    ),
                },
                "project": {
                    "type": "string",
                    "description": (
                        "Project identifier (for store_memory, get_timeline)."
                    ),
                },
                "discovery_tokens": {
                    "type": "integer",
                    "description": (
                        "Estimated token cost of the discovery (for store_memory)."
                    ),
                },
                "file_path": {
                    "type": "string",
                    "description": "File path to search for (for search_by_file).",
                },
                "concept": {
                    "type": "string",
                    "enum": CONCEPT_TYPES,
                    "description": "Concept to search for (for search_by_concept).",
                },
                # -- Fact fields (unchanged) --
                "subject": {
                    "type": "string",
                    "description": (
                        "Fact subject (for store_fact / query_facts)."
                    ),
                },
                "predicate": {
                    "type": "string",
                    "description": (
                        "Fact predicate (for store_fact / query_facts)."
                    ),
                },
                "object_value": {
                    "type": "string",
                    "description": (
                        "Fact object value (for store_fact / query_facts)."
                    ),
                },
                "confidence": {
                    "type": "number",
                    "description": (
                        "Confidence 0-1 for a fact triple (for store_fact)."
                    ),
                },
                "source_entry_id": {
                    "type": "string",
                    "description": (
                        "Memory id that sourced this fact (for store_fact)."
                    ),
                },
                "fact_id": {
                    "type": "string",
                    "description": "Fact id (for delete_fact).",
                },
                "min_confidence": {
                    "type": "number",
                    "description": (
                        "Minimum confidence filter (for query_facts)."
                    ),
                },
                "max_age_days": {
                    "type": "number",
                    "description": (
                        "Max age in days for summarize_old (default 30)."
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
                    title=input.get("title", ""),
                    subtitle=input.get("subtitle", ""),
                    type=input.get("type", "change"),
                    concepts=input.get("concepts"),
                    files_read=input.get("files_read"),
                    files_modified=input.get("files_modified"),
                    session_id=input.get("session_id"),
                    project=input.get("project"),
                    discovery_tokens=int(input.get("discovery_tokens", 0)),
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
                records = self._store.get([mem_id], _increment_access=True)
                if not records:
                    return ToolResult(
                        success=False,
                        error={"message": f"memory {mem_id} not found"},
                    )
                return ToolResult(success=True, output=records[0])

            if op == "update_memory":
                mem_id = input.get("id", "")
                if not mem_id:
                    return ToolResult(
                        success=False,
                        error={"message": "id is required for update_memory"},
                    )
                importance_raw = input.get("importance")
                trust_raw = input.get("trust")
                updated = self._store.update(
                    mem_id,
                    content=input.get("content"),
                    title=input.get("title"),
                    subtitle=input.get("subtitle"),
                    type=input.get("type"),
                    concepts=input.get("concepts"),
                    files_read=input.get("files_read"),
                    files_modified=input.get("files_modified"),
                    category=input.get("category"),
                    importance=float(importance_raw) if importance_raw is not None else None,
                    tags=input.get("tags"),
                    sensitivity=input.get("sensitivity"),
                    trust=float(trust_raw) if trust_raw is not None else None,
                )
                if updated is None:
                    return ToolResult(
                        success=False,
                        error={"message": f"memory {mem_id} not found"},
                    )
                return ToolResult(
                    success=True,
                    output={"memory": updated, "status": "updated"},
                )

            if op == "delete_memory":
                mem_id = input.get("id", "")
                if not mem_id:
                    return ToolResult(
                        success=False,
                        error={"message": "id is required for delete_memory"},
                    )
                deleted = self._store.delete(mem_id)
                return ToolResult(success=True, output={"deleted": deleted})

            if op == "search_by_file":
                file_path = input.get("file_path", "")
                if not file_path:
                    return ToolResult(
                        success=False,
                        error={"message": "file_path is required for search_by_file"},
                    )
                results = self._store.search_by_file(
                    file_path, limit=int(input.get("limit", 10))
                )
                return ToolResult(
                    success=True,
                    output={
                        "file_path": file_path,
                        "results": results,
                        "count": len(results),
                    },
                )

            if op == "search_by_concept":
                concept = input.get("concept", "")
                if not concept:
                    return ToolResult(
                        success=False,
                        error={"message": "concept is required for search_by_concept"},
                    )
                results = self._store.search_by_concept(
                    concept, limit=int(input.get("limit", 10))
                )
                return ToolResult(
                    success=True,
                    output={
                        "concept": concept,
                        "results": results,
                        "count": len(results),
                    },
                )

            if op == "get_timeline":
                results = self._store.get_timeline(
                    limit=int(input.get("limit", 50)),
                    type=input.get("type"),
                    project=input.get("project"),
                    session_id=input.get("session_id"),
                )
                return ToolResult(
                    success=True,
                    output={"memories": results, "count": len(results)},
                )

            if op == "purge_expired":
                count = self._store.purge_expired()
                return ToolResult(
                    success=True, output={"purged": count}
                )

            # -- Fact operations ------------------------------------------------

            if op == "store_fact":
                subject = input.get("subject", "")
                predicate = input.get("predicate", "")
                obj = input.get("object_value", "")
                if not subject or not predicate or not obj:
                    return ToolResult(
                        success=False,
                        error={
                            "message": (
                                "subject, predicate, and object_value are "
                                "required for store_fact"
                            )
                        },
                    )
                fact_id = self._store.store_fact(
                    subject=subject,
                    predicate=predicate,
                    object_value=obj,
                    confidence=float(input.get("confidence", 1.0)),
                    source_entry_id=input.get("source_entry_id"),
                )
                return ToolResult(
                    success=True, output={"fact_id": fact_id, "status": "stored"}
                )

            if op == "query_facts":
                facts = self._store.query_facts(
                    subject=input.get("subject"),
                    predicate=input.get("predicate"),
                    object_value=input.get("object_value"),
                    min_confidence=float(input.get("min_confidence", 0.0)),
                    limit=int(input.get("limit", 50)),
                )
                return ToolResult(
                    success=True,
                    output={"facts": facts, "count": len(facts)},
                )

            if op == "delete_fact":
                fact_id = input.get("fact_id", "")
                if not fact_id:
                    return ToolResult(
                        success=False,
                        error={"message": "fact_id is required for delete_fact"},
                    )
                deleted = self._store.delete_fact(fact_id)
                return ToolResult(success=True, output={"deleted": deleted})

            # -- Summarization --------------------------------------------------

            if op == "summarize_old":
                stats = self._store.summarize_old(
                    max_age_days=float(input.get("max_age_days", 30)),
                    max_memories=int(input.get("limit", 5)),
                )
                return ToolResult(success=True, output=stats)

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
    max_memories = int(cfg.get("max_memories", 0))

    store = MemoryStore(db_path, max_memories=max_memories)
    tool = MemoryTool(store)

    # Register as Tool (LLM-callable)
    await coordinator.mount("tools", tool, name="tool-memory-store")

    # Register as capability (so hooks-memory-inject auto-discovers it)
    coordinator.register_capability("memory.store", store)

    logger.info(
        "tool-memory-store mounted (db: %s, max_memories: %s)",
        db_path,
        max_memories if max_memories > 0 else "unlimited",
    )
