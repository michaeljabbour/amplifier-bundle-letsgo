"""Memorability scoring for selective memory encoding.

Inspired by neuroscience research showing most real-world experience is
never stored (55.7% recognition rate). Memorability is predictable from
content features: emotional valence, distinctiveness, and substance.

This is a pure capability module — no hook events. The capture hook
consults memory.memorability to decide whether to store observations.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

__amplifier_module_type__ = "hook"


class MemorabilityScorer:
    """Predicts whether content is worth storing as a long-term memory.

    Scoring features:
      1. Substance (0-1): Content length and structure signal.
      2. Salience (0-1): Error keywords, success markers, emotional valence.
      3. Distinctiveness (0-1): Low overlap with recent memories.
      4. Type weight (0-1): Discoveries and bugfixes > routine changes.
    """

    TYPE_MEMORABILITY: dict[str, float] = {
        "bugfix": 0.85,
        "discovery": 0.90,
        "decision": 0.80,
        "feature": 0.60,
        "refactor": 0.45,
        "change": 0.35,
        "session_summary": 0.70,
        "compressed_summary": 0.60,
    }

    SALIENCE_KEYWORDS: set[str] = {
        "error",
        "bug",
        "fix",
        "crash",
        "fail",
        "broken",
        "critical",
        "security",
        "vulnerability",
        "resolved",
        "root cause",
        "workaround",
        "breakthrough",
        "discovered",
        "important",
        "warning",
        "exception",
        "traceback",
        "panic",
        "fatal",
        "success",
        "passed",
        "verified",
    }

    def __init__(
        self,
        store: Any,
        *,
        base_threshold: float = 0.30,
        distinctiveness_weight: float = 0.30,
        salience_weight: float = 0.25,
        substance_weight: float = 0.25,
        type_weight: float = 0.20,
    ) -> None:
        self._store = store
        self._threshold = base_threshold
        self._w_distinct = distinctiveness_weight
        self._w_salience = salience_weight
        self._w_substance = substance_weight
        self._w_type = type_weight

    def score(
        self,
        content: str,
        *,
        tool_name: str = "",
        observation_type: str = "change",
        has_error: bool = False,
        file_count: int = 0,
    ) -> float:
        """Score content memorability from 0.0 to 1.0."""
        substance = self._score_substance(content, file_count)
        salience = self._score_salience(content, has_error)
        distinctiveness = self._score_distinctiveness(content)
        type_score = self.TYPE_MEMORABILITY.get(observation_type, 0.40)

        total = (
            self._w_substance * substance
            + self._w_salience * salience
            + self._w_distinct * distinctiveness
            + self._w_type * type_score
        )
        return max(0.0, min(1.0, total))

    def should_store(self, score: float) -> bool:
        """Returns True if the score meets the storage threshold."""
        return score >= self._threshold

    def _score_substance(self, content: str, file_count: int) -> float:
        length = len(content)
        if length < 50:
            return 0.1
        if length < 200:
            return 0.3
        if length < 500:
            return 0.5
        base = min(0.8, 0.5 + (length - 500) / 5000)
        if file_count > 0:
            base = min(1.0, base + 0.1)
        return base

    def _score_salience(self, content: str, has_error: bool) -> float:
        if has_error:
            return 0.9
        lower = content.lower()
        hits = sum(1 for kw in self.SALIENCE_KEYWORDS if kw in lower)
        return min(1.0, hits * 0.2)

    def _score_distinctiveness(self, content: str) -> float:
        """How different is this from what's already stored?"""
        try:
            similar = self._store.search_v2(content, limit=1, candidate_limit=5)
            if not similar:
                return 0.9
            top_score = similar[0].get("_score", 0.5)
            return max(0.0, 1.0 - top_score)
        except Exception:
            return 0.5


async def mount(coordinator: Any, config: dict[str, Any] | None = None) -> None:
    """Mount the memorability scorer as a capability."""
    store = coordinator.get_capability("memory.store")
    if store is None:
        logger.info("memory.store not available; memorability scoring disabled")
        return

    cfg = config or {}
    scorer = MemorabilityScorer(
        store=store,
        base_threshold=cfg.get("base_threshold", 0.30),
        distinctiveness_weight=cfg.get("distinctiveness_weight", 0.30),
        salience_weight=cfg.get("salience_weight", 0.25),
        substance_weight=cfg.get("substance_weight", 0.25),
        type_weight=cfg.get("type_weight", 0.20),
    )
    coordinator.register_capability("memory.memorability", scorer)
