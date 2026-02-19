"""Compositional memory compression via cluster-and-merge.

Inspired by CRUMB (Compositional Replay Using Memory Blocks) which achieves
96% compression by reconstructing features from reusable block vectors.

This simpler analog clusters similar old memories by keyword overlap and
merges redundant clusters into compressed summaries. Runs at session:end
after consolidation has adjusted importance scores.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

__amplifier_module_type__ = "hook"

# Canonical stopwords — shared with boundaries and store modules
_STOPS = frozenset({
    "a", "all", "also", "an", "and", "are", "as", "at",
    "be", "been", "but", "by", "can", "each", "for", "from",
    "has", "have", "how", "i", "in", "into", "is", "it",
    "its", "just", "me", "more", "my", "not", "of", "on",
    "one", "or", "our", "out", "so", "some", "than", "that",
    "the", "this", "to", "was", "we", "what", "when", "who",
    "will", "with", "you", "your",
})


def _extract_keywords(text: str, max_keywords: int = 12) -> set[str]:
    """Extract meaningful keywords from text."""
    words = re.findall(r"[a-z_][a-z0-9_]{2,}", text.lower())
    filtered = [w for w in words if w not in _STOPS]
    counts: dict[str, int] = {}
    for w in filtered:
        counts[w] = counts.get(w, 0) + 1
    ranked = sorted(counts, key=lambda k: counts[k], reverse=True)
    return set(ranked[:max_keywords])


class MemoryCompressor:
    """Clusters similar old memories and merges them into compressed summaries.

    Algorithm:
      1. Fetch memories older than min_age_days
      2. Extract keywords for each memory
      3. Greedy clustering: group memories with Jaccard similarity > threshold
      4. For clusters >= min_cluster_size: merge into summary, delete originals
      5. Single/small-cluster memories are left untouched
    """

    def __init__(
        self,
        store: Any,
        *,
        similarity_threshold: float = 0.50,
        min_cluster_size: int = 3,
        min_age_days: float = 7.0,
        max_batch_size: int = 200,
    ) -> None:
        self._store = store
        self._sim_threshold = similarity_threshold
        self._min_cluster = min_cluster_size
        self._min_age_days = min_age_days
        self._max_batch = max_batch_size

    @property
    def name(self) -> str:
        return "memory-compression"

    async def execute(self, event: str, data: dict[str, Any]) -> dict[str, Any]:
        """Run compression at session end."""
        try:
            stats = self.compress()
            if stats["clusters_merged"] > 0:
                logger.info(
                    "Compression: merged %d clusters (%d memories → %d summaries)",
                    stats["clusters_merged"], stats["memories_removed"],
                    stats["summaries_created"],
                )
            return {"action": "continue", "compression_stats": stats}
        except Exception as e:
            logger.debug("Compression error (non-blocking): %s", e)
            return {"action": "continue"}

    def compress(self) -> dict[str, int]:
        """Run a full compression pass."""
        stats = {
            "total_candidates": 0, "clusters_found": 0,
            "clusters_merged": 0, "memories_removed": 0,
            "summaries_created": 0,
        }

        cutoff = datetime.now(timezone.utc) - timedelta(days=self._min_age_days)
        candidates = self._get_old_memories(cutoff)
        stats["total_candidates"] = len(candidates)

        if len(candidates) < self._min_cluster:
            return stats

        keyword_map: dict[str, set[str]] = {}
        for mem in candidates:
            text = f"{mem.get('title', '')} {mem.get('content_preview', '')} {mem.get('content', '')}"
            keyword_map[mem["id"]] = _extract_keywords(text)

        clusters = self._cluster_by_similarity(candidates, keyword_map)
        stats["clusters_found"] = len(clusters)

        for cluster in clusters:
            if len(cluster) >= self._min_cluster:
                summary_id = self._merge_cluster(cluster, keyword_map)
                if summary_id:
                    stats["clusters_merged"] += 1
                    stats["summaries_created"] += 1
                    stats["memories_removed"] += len(cluster)

        return stats

    def _get_old_memories(self, cutoff: datetime) -> list[dict[str, Any]]:
        """Fetch memories older than cutoff."""
        all_memories = self._store.list_all(limit=self._max_batch, offset=0)
        cutoff_str = cutoff.isoformat()
        return [
            m for m in all_memories
            if m.get("created_at", "") < cutoff_str
            and m.get("type") not in ("session_summary", "compressed_summary")
        ]

    def _cluster_by_similarity(
        self,
        memories: list[dict[str, Any]],
        keyword_map: dict[str, set[str]],
    ) -> list[list[dict[str, Any]]]:
        """Greedy single-linkage clustering by keyword Jaccard similarity."""
        assigned: set[str] = set()
        clusters: list[list[dict[str, Any]]] = []

        for mem in memories:
            if mem["id"] in assigned:
                continue

            cluster = [mem]
            assigned.add(mem["id"])
            kw_a = keyword_map.get(mem["id"], set())

            for other in memories:
                if other["id"] in assigned:
                    continue
                kw_b = keyword_map.get(other["id"], set())
                if self._jaccard(kw_a, kw_b) >= self._sim_threshold:
                    cluster.append(other)
                    assigned.add(other["id"])

            clusters.append(cluster)

        return clusters

    @staticmethod
    def _jaccard(a: set[str], b: set[str]) -> float:
        if not a and not b:
            return 1.0
        if not a or not b:
            return 0.0
        return len(a & b) / len(a | b)

    def _merge_cluster(
        self,
        cluster: list[dict[str, Any]],
        keyword_map: dict[str, set[str]],
    ) -> str | None:
        """Create a merged summary from a cluster and delete originals."""
        if not cluster:
            return None

        max_importance = max(m.get("importance", 0.5) for m in cluster)
        all_tags: set[str] = set()
        all_concepts: set[str] = set()
        all_files_read: set[str] = set()
        all_files_modified: set[str] = set()
        titles: list[str] = []

        for mem in cluster:
            # Parse tags
            tags_raw = mem.get("tags", "")
            if isinstance(tags_raw, str) and tags_raw:
                if tags_raw.startswith("["):
                    try:
                        all_tags.update(json.loads(tags_raw))
                    except (json.JSONDecodeError, TypeError):
                        all_tags.update(t.strip() for t in tags_raw.split(",") if t.strip())
                else:
                    all_tags.update(t.strip() for t in tags_raw.split(",") if t.strip())

            # Parse concepts
            concepts_raw = mem.get("concepts", "[]")
            if isinstance(concepts_raw, str):
                try:
                    all_concepts.update(json.loads(concepts_raw))
                except (json.JSONDecodeError, TypeError):
                    pass

            # Parse files
            for field_name, target_set in [("files_read", all_files_read), ("files_modified", all_files_modified)]:
                raw = mem.get(field_name, "[]")
                if isinstance(raw, str):
                    try:
                        target_set.update(json.loads(raw))
                    except (json.JSONDecodeError, TypeError):
                        pass
                elif isinstance(raw, list):
                    target_set.update(raw)

            if mem.get("title"):
                titles.append(mem["title"])

        # Build compressed content
        contents = []
        for m in cluster:
            c = m.get("content") or m.get("content_preview", "")
            if c:
                contents.append(c)

        summary_content = f"Compressed from {len(cluster)} related memories.\n\n"
        summary_content += "\n---\n".join(c[:200] for c in contents[:5])
        if len(contents) > 5:
            summary_content += f"\n\n(+{len(contents) - 5} more)"

        try:
            summary_id = self._store.store(
                content=summary_content,
                type="compressed_summary",
                title=f"Compressed: {titles[0] if titles else 'related memories'}",
                subtitle=f"Merged {len(cluster)} memories: {', '.join(titles[:3])}",
                importance=max_importance,
                tags=list(all_tags) if all_tags else [],
                concepts=list(all_concepts) if all_concepts else [],
                files_read=list(all_files_read) if all_files_read else [],
                files_modified=list(all_files_modified) if all_files_modified else [],
            )

            for mem in cluster:
                try:
                    self._store.delete(mem["id"])
                except Exception:
                    pass

            return summary_id
        except Exception as e:
            logger.debug("Failed to merge cluster: %s", e)
            return None


async def mount(coordinator: Any, config: dict[str, Any] | None = None) -> None:
    """Mount the compression hook."""
    store = coordinator.get_capability("memory.store")
    if store is None:
        logger.info("memory.store not available; compression disabled")
        return

    cfg = config or {}
    compressor = MemoryCompressor(
        store=store,
        similarity_threshold=cfg.get("similarity_threshold", 0.50),
        min_cluster_size=cfg.get("min_cluster_size", 3),
        min_age_days=cfg.get("min_age_days", 7.0),
        max_batch_size=cfg.get("max_batch_size", 200),
    )

    coordinator.hooks.register(
        event="session:end",
        handler=compressor.execute,
        priority=300,
        name="memory-compression.session_end",
    )
    coordinator.register_capability("memory.compression", compressor)
