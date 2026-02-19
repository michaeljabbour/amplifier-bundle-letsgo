"""Multi-scale temporal scaffolding for balanced memory retrieval.

Inspired by Temporally Periodic Cells in human entorhinal cortex that
fire at multiple timescales (62.5s to 400s), providing a temporal analog
of spatial grid cells.

Instead of returning only top-N most relevant memories (which biases
toward recent or high-importance), this distributes retrieval across
temporal scales: immediate, task, session, and project.

This is a pure capability module — no hook events. The inject hook
uses memory.temporal for balanced retrieval when available.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

__amplifier_module_type__ = "hook"


def _parse_dt(value: Any) -> datetime | None:
    """Parse ISO datetime string to timezone-aware datetime."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


class TemporalScaffold:
    """Multi-scale temporal retrieval for balanced memory context.

    Distributes retrieval across temporal scales to give the agent both
    immediate context and long-term wisdom.

    Default allocation: 1 immediate + 2 task + 1 session + 1 project = 5 total
    """

    DEFAULT_BOUNDARIES: dict[str, float] = {
        "immediate": 300.0,    # 5 minutes
        "task": 1800.0,        # 30 minutes
        "session": 7200.0,     # 2 hours
    }

    DEFAULT_ALLOCATION: dict[str, int] = {
        "immediate": 1,
        "task": 2,
        "session": 1,
        "project": 1,
    }

    def __init__(
        self,
        store: Any,
        *,
        allocation: dict[str, int] | None = None,
        scale_boundaries: dict[str, float] | None = None,
    ) -> None:
        self._store = store
        self._allocation = allocation or dict(self.DEFAULT_ALLOCATION)
        self._boundaries = scale_boundaries or dict(self.DEFAULT_BOUNDARIES)

    def classify_scale(
        self,
        memory: dict[str, Any],
        reference_time: datetime | None = None,
    ) -> str:
        """Classify a memory's temporal scale relative to reference_time."""
        ref = reference_time or datetime.now(timezone.utc)
        created = _parse_dt(memory.get("created_at"))
        if created is None:
            return "project"

        age_seconds = max(0.0, (ref - created).total_seconds())

        if age_seconds < self._boundaries.get("immediate", 300.0):
            return "immediate"
        elif age_seconds < self._boundaries.get("task", 1800.0):
            return "task"
        elif age_seconds < self._boundaries.get("session", 7200.0):
            return "session"
        else:
            return "project"

    def balanced_retrieve(
        self,
        prompt: str,
        *,
        scoring: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve memories balanced across temporal scales.

        Algorithm:
          1. Fetch a broad candidate set from the store
          2. Classify each by temporal scale
          3. Select top-N from each scale per allocation
          4. Backfill from any scale if some scales are empty
        """
        total_needed = sum(self._allocation.values())
        candidate_limit = max(30, total_needed * 5)

        candidates = self._store.search_v2(
            prompt, limit=candidate_limit, candidate_limit=candidate_limit,
            scoring=scoring,
        )

        # Bucket by temporal scale
        now = datetime.now(timezone.utc)
        buckets: dict[str, list[dict[str, Any]]] = {
            scale: [] for scale in self._allocation
        }
        for mem in candidates:
            scale = self.classify_scale(mem, reference_time=now)
            if scale in buckets:
                buckets[scale].append(mem)

        # Select top-N from each bucket (already ranked by relevance)
        result: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for scale, limit in self._allocation.items():
            for mem in buckets.get(scale, [])[:limit]:
                if mem.get("id") and mem["id"] not in seen_ids:
                    mem["_temporal_scale"] = scale
                    result.append(mem)
                    seen_ids.add(mem["id"])

        # Backfill if any scale was underfilled
        remaining = total_needed - len(result)
        if remaining > 0:
            for mem in candidates:
                mid = mem.get("id")
                if mid and mid not in seen_ids:
                    result.append(mem)
                    seen_ids.add(mid)
                    remaining -= 1
                    if remaining <= 0:
                        break

        return result


async def mount(coordinator: Any, config: dict[str, Any] | None = None) -> None:
    """Mount the temporal scaffold as a capability."""
    store = coordinator.get_capability("memory.store")
    if store is None:
        logger.info("memory.store not available; temporal scaffolding disabled")
        return

    cfg = config or {}
    scaffold = TemporalScaffold(
        store=store,
        allocation=cfg.get("allocation"),
        scale_boundaries=cfg.get("scale_boundaries"),
    )
    coordinator.register_capability("memory.temporal", scaffold)
