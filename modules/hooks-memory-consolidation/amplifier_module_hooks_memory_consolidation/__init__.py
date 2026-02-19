"""Self-amplifying memory consolidation.

Inspired by stochastic self-amplifying replay in biological memory:
retrieved memories get replayed more, strengthening them further.
Memory lifetimes become orders of magnitude longer than base decay.

At session end, runs a consolidation pass:
  - Boost importance for accessed memories (logarithmic with access count)
  - Decay importance for unaccessed memories (linear with age)
  - Remove old unaccessed memories below min_importance threshold
  - Protected types (decisions, discoveries) decay at half rate
"""
from __future__ import annotations

import logging
import math
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


class MemoryConsolidator:
    """Self-amplifying consolidation: boost accessed memories, decay unused ones.

    The virtuous cycle:
      1. Relevant memories get retrieved by search_v2() → accessed_count increases
      2. At session end, consolidation boosts importance for accessed memories
      3. Higher importance → ranked higher in future searches → more access
      4. Unused memories decay → eventually fall below min_importance → purged
    """

    def __init__(
        self,
        store: Any,
        *,
        decay_rate: float = 0.02,
        access_boost_factor: float = 0.03,
        min_importance: float = 0.05,
        max_unaccessed_age_days: float = 90.0,
        protected_types: list[str] | None = None,
    ) -> None:
        self._store = store
        self._decay_rate = decay_rate
        self._boost_factor = access_boost_factor
        self._min_importance = min_importance
        self._max_unaccessed_age = max_unaccessed_age_days
        self._protected_types = set(protected_types or ["decision", "discovery"])

    @property
    def name(self) -> str:
        return "memory-consolidation"

    async def execute(self, event: str, data: dict[str, Any]) -> dict[str, Any]:
        """Run consolidation at session end."""
        try:
            stats = self.consolidate()
            logger.info(
                "Consolidation complete: boosted=%d decayed=%d removed=%d",
                stats["boosted"], stats["decayed"], stats["removed"],
            )
            return {"action": "continue", "consolidation_stats": stats}
        except Exception as e:
            logger.debug("Consolidation error (non-blocking): %s", e)
            return {"action": "continue"}

    def consolidate(self) -> dict[str, int]:
        """Run a full consolidation pass over all memories."""
        stats = {"boosted": 0, "decayed": 0, "removed": 0, "total_processed": 0}
        now = datetime.now(timezone.utc)

        offset = 0
        batch_size = 100
        while True:
            memories = self._store.list_all(limit=batch_size, offset=offset)
            if not memories:
                break

            for mem in memories:
                stats["total_processed"] += 1
                action = self._process_memory(mem, now)
                if action:
                    stats[action] += 1

            if len(memories) < batch_size:
                break
            offset += batch_size

        # Also purge expired memories
        try:
            self._store.purge_expired()
        except Exception:
            pass

        return stats

    def _process_memory(self, mem: dict[str, Any], now: datetime) -> str | None:
        """Process a single memory. Returns 'boosted', 'decayed', 'removed', or None."""
        mem_id = mem.get("id")
        if not mem_id:
            return None

        importance = mem.get("importance", 0.5)
        accessed_count = mem.get("accessed_count", 0)
        mem_type = mem.get("type", "change")
        updated_at = _parse_dt(mem.get("updated_at"))

        if updated_at is None:
            return None

        days_since_update = max(0.0, (now - updated_at).total_seconds() / 86400.0)
        is_protected = mem_type in self._protected_types

        if accessed_count > 0:
            # BOOST: importance += boost_factor * log(1 + accessed_count)
            boost = self._boost_factor * math.log1p(accessed_count)
            new_importance = min(1.0, importance + boost)
            if abs(new_importance - importance) > 0.001:
                try:
                    self._store.update(mem_id, importance=new_importance)
                except Exception:
                    pass
                return "boosted"
        else:
            # DECAY: unaccessed memories lose importance over time
            rate = self._decay_rate * (0.5 if is_protected else 1.0)
            decay = rate * days_since_update
            new_importance = max(0.0, importance - decay)

            if new_importance < self._min_importance and days_since_update > self._max_unaccessed_age:
                try:
                    self._store.delete(mem_id)
                except Exception:
                    pass
                return "removed"
            elif abs(new_importance - importance) > 0.001:
                try:
                    self._store.update(mem_id, importance=new_importance)
                except Exception:
                    pass
                return "decayed"

        return None


async def mount(coordinator: Any, config: dict[str, Any] | None = None) -> None:
    """Mount the consolidation hook."""
    store = coordinator.get_capability("memory.store")
    if store is None:
        logger.info("memory.store not available; consolidation disabled")
        return

    cfg = config or {}
    consolidator = MemoryConsolidator(
        store=store,
        decay_rate=cfg.get("decay_rate", 0.02),
        access_boost_factor=cfg.get("access_boost_factor", 0.03),
        min_importance=cfg.get("min_importance", 0.05),
        max_unaccessed_age_days=cfg.get("max_unaccessed_age_days", 90.0),
        protected_types=cfg.get("protected_types", ["decision", "discovery"]),
    )

    coordinator.hooks.register(
        event="session:end",
        handler=consolidator.execute,
        priority=200,
        name="memory-consolidation.session_end",
    )
    coordinator.register_capability("memory.consolidation", consolidator)
