"""Tests for hooks-memory-memorability module.

Covers the MemorabilityScorer: mount registration, salience scoring,
substance scoring, type-based scoring, distinctiveness, threshold gating,
and configurable weights.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from amplifier_module_hooks_memory_memorability import MemorabilityScorer, mount
from amplifier_module_tool_memory_store import MemoryStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(tmp_path / "test_memories.db")


def _make_scorer(
    tmp_path: Path,
    *,
    base_threshold: float = 0.30,
    distinctiveness_weight: float = 0.30,
    salience_weight: float = 0.25,
    substance_weight: float = 0.25,
    type_weight: float = 0.20,
    seed_data: bool = False,
) -> tuple[MemorabilityScorer, MemoryStore]:
    store = _make_store(tmp_path)
    if seed_data:
        store.store("Existing memory about Python asyncio patterns and coroutines")
        store.store("Another memory about Docker container networking setup")
    scorer = MemorabilityScorer(
        store,
        base_threshold=base_threshold,
        distinctiveness_weight=distinctiveness_weight,
        salience_weight=salience_weight,
        substance_weight=substance_weight,
        type_weight=type_weight,
    )
    return scorer, store


# ===========================================================================
# Mount tests
# ===========================================================================


class TestMount:
    """Tests for mount() registration."""

    @pytest.mark.asyncio
    async def test_mount_registers_capability(
        self, tmp_path: Path, mock_coordinator: Any
    ) -> None:
        store = _make_store(tmp_path)
        mock_coordinator.register_capability("memory.store", store)

        await mount(mock_coordinator, config={})

        assert "memory.memorability" in mock_coordinator.capabilities
        cap = mock_coordinator.capabilities["memory.memorability"]
        assert isinstance(cap, MemorabilityScorer)

    @pytest.mark.asyncio
    async def test_mount_without_store_skips(self, mock_coordinator: Any) -> None:
        await mount(mock_coordinator, config={})
        assert "memory.memorability" not in mock_coordinator.capabilities


# ===========================================================================
# Salience scoring tests
# ===========================================================================


class TestSalience:
    """Tests for salience scoring (error detection, keyword presence)."""

    def test_high_salience_error(self, tmp_path: Path) -> None:
        """has_error=True should produce a high salience score."""
        scorer, _ = _make_scorer(tmp_path)
        score = scorer._score_salience("Normal content without keywords", has_error=True)
        assert score >= 0.9

    def test_salience_with_keywords(self, tmp_path: Path) -> None:
        """Content with salience keywords should score higher."""
        scorer, _ = _make_scorer(tmp_path)

        score_with = scorer._score_salience(
            "Found a critical error causing crash in production", has_error=False
        )
        score_without = scorer._score_salience(
            "Normal routine update to documentation files", has_error=False
        )
        assert score_with > score_without

    def test_salience_no_keywords_no_error(self, tmp_path: Path) -> None:
        """Content with no salience keywords and no error should score low."""
        scorer, _ = _make_scorer(tmp_path)
        score = scorer._score_salience(
            "Just a regular note about something ordinary", has_error=False
        )
        assert score < 0.5


# ===========================================================================
# Substance scoring tests
# ===========================================================================


class TestSubstance:
    """Tests for substance scoring (content length)."""

    def test_low_substance_short_content(self, tmp_path: Path) -> None:
        """Short content (< 50 chars) should have low substance score."""
        scorer, _ = _make_scorer(tmp_path)
        score = scorer._score_substance("Short", file_count=0)
        assert score <= 0.15

    def test_medium_substance(self, tmp_path: Path) -> None:
        """Medium content (100-200 chars) should score 0.3."""
        scorer, _ = _make_scorer(tmp_path)
        content = "x" * 150
        score = scorer._score_substance(content, file_count=0)
        assert score == pytest.approx(0.3)

    def test_high_substance_long_content(self, tmp_path: Path) -> None:
        """Long content (500+ chars) should have high substance score."""
        scorer, _ = _make_scorer(tmp_path)
        content = "x" * 600
        score = scorer._score_substance(content, file_count=0)
        assert score >= 0.5

    def test_substance_file_count_boost(self, tmp_path: Path) -> None:
        """Having files involved should boost substance score for long content.

        The +0.1 file_count boost only applies when content >= 500 chars.
        """
        scorer, _ = _make_scorer(tmp_path)
        content = "x" * 600  # Must be >= 500 for file_count boost to apply
        score_no_files = scorer._score_substance(content, file_count=0)
        score_with_files = scorer._score_substance(content, file_count=3)
        assert score_with_files > score_no_files
        assert score_with_files - score_no_files == pytest.approx(0.1, abs=0.01)


# ===========================================================================
# Type scoring tests
# ===========================================================================


class TestTypeScoring:
    """Tests for observation type-based scoring."""

    def test_bugfix_type_high_memorability(self, tmp_path: Path) -> None:
        """bugfix observation should have high type score."""
        scorer, _ = _make_scorer(tmp_path)
        score = scorer.score(
            "x" * 200,
            observation_type="bugfix",
        )
        # bugfix type score = 0.85, contributing significantly
        assert score > 0.3

    def test_change_type_low_memorability(self, tmp_path: Path) -> None:
        """change observation should have lower type score."""
        scorer, _ = _make_scorer(tmp_path)
        score_change = scorer.score(
            "x" * 200,
            observation_type="change",
        )
        score_bugfix = scorer.score(
            "x" * 200,
            observation_type="bugfix",
        )
        assert score_bugfix > score_change

    def test_discovery_type_highest(self, tmp_path: Path) -> None:
        """discovery type should have the highest type memorability."""
        scorer, _ = _make_scorer(tmp_path)
        score = scorer.score(
            "x" * 200,
            observation_type="discovery",
        )
        assert score > 0.3

    def test_unknown_type_defaults(self, tmp_path: Path) -> None:
        """Unknown observation type should not crash and use a default."""
        scorer, _ = _make_scorer(tmp_path)
        score = scorer.score(
            "x" * 200,
            observation_type="unknown_type",
        )
        assert 0.0 <= score <= 1.0


# ===========================================================================
# Distinctiveness scoring tests
# ===========================================================================


class TestDistinctiveness:
    """Tests for distinctiveness scoring (novelty detection)."""

    def test_distinctiveness_novel_content(self, tmp_path: Path) -> None:
        """Content with no similar existing memories should score high."""
        scorer, _ = _make_scorer(tmp_path)
        # Empty store means nothing similar exists
        score = scorer._score_distinctiveness(
            "Completely novel content about quantum computing algorithms"
        )
        assert score >= 0.8

    def test_distinctiveness_redundant_content(self, tmp_path: Path) -> None:
        """Content matching existing memories should score low."""
        scorer, store = _make_scorer(tmp_path, seed_data=True)

        # Search for content very similar to what's already stored
        score = scorer._score_distinctiveness(
            "Python asyncio patterns and coroutines for concurrent programming"
        )
        # Should be lower than novel content since similar memory exists
        novel_score = scorer._score_distinctiveness(
            "Completely unique topic about underwater basket weaving techniques"
        )
        assert score <= novel_score

    def test_distinctiveness_exception_handling(self, tmp_path: Path) -> None:
        """Distinctiveness should return 0.5 on store exceptions."""
        class BrokenStore:
            def search_v2(self, *args, **kwargs):
                raise RuntimeError("Store is broken")

        scorer = MemorabilityScorer(BrokenStore())
        score = scorer._score_distinctiveness("Any content here")
        assert score == 0.5


# ===========================================================================
# Should-store threshold tests
# ===========================================================================


class TestShouldStore:
    """Tests for the should_store threshold method."""

    def test_should_store_above_threshold(self, tmp_path: Path) -> None:
        scorer, _ = _make_scorer(tmp_path, base_threshold=0.30)
        assert scorer.should_store(0.50) is True
        assert scorer.should_store(0.31) is True
        assert scorer.should_store(1.0) is True

    def test_should_store_below_threshold(self, tmp_path: Path) -> None:
        scorer, _ = _make_scorer(tmp_path, base_threshold=0.30)
        assert scorer.should_store(0.10) is False
        assert scorer.should_store(0.0) is False

    def test_should_store_at_threshold(self, tmp_path: Path) -> None:
        scorer, _ = _make_scorer(tmp_path, base_threshold=0.30)
        assert scorer.should_store(0.30) is True


# ===========================================================================
# Configurable weights tests
# ===========================================================================


class TestConfigurableWeights:
    """Tests for custom scoring weights."""

    def test_scoring_weights_configurable(self, tmp_path: Path) -> None:
        """Custom weights should change the final score."""
        # All weight on type: bugfix should dominate
        scorer_type_heavy, _ = _make_scorer(
            tmp_path,
            type_weight=1.0,
            salience_weight=0.0,
            substance_weight=0.0,
            distinctiveness_weight=0.0,
        )
        score_bugfix = scorer_type_heavy.score("short", observation_type="bugfix")
        score_change = scorer_type_heavy.score("short", observation_type="change")
        assert score_bugfix > score_change

        # All weight on salience: error flag should dominate
        scorer_salience_heavy, _ = _make_scorer(
            tmp_path,
            type_weight=0.0,
            salience_weight=1.0,
            substance_weight=0.0,
            distinctiveness_weight=0.0,
        )
        score_error = scorer_salience_heavy.score(
            "short", has_error=True, observation_type="change"
        )
        score_no_error = scorer_salience_heavy.score(
            "short", has_error=False, observation_type="change"
        )
        assert score_error > score_no_error

    def test_score_clamped_zero_to_one(self, tmp_path: Path) -> None:
        """Final score should always be in [0.0, 1.0]."""
        scorer, _ = _make_scorer(
            tmp_path,
            type_weight=5.0,
            salience_weight=5.0,
            substance_weight=5.0,
            distinctiveness_weight=5.0,
        )
        score = scorer.score(
            "x" * 1000,
            has_error=True,
            observation_type="discovery",
        )
        assert 0.0 <= score <= 1.0


# ===========================================================================
# Integration score tests
# ===========================================================================


class TestIntegrationScore:
    """End-to-end scoring tests combining all components."""

    def test_high_memorability_content(self, tmp_path: Path) -> None:
        """Content with error, long, bugfix type, novel -> high score."""
        scorer, _ = _make_scorer(tmp_path)
        score = scorer.score(
            "x" * 600 + " error crash critical bug fix resolved",
            has_error=True,
            observation_type="bugfix",
        )
        assert score > 0.5

    def test_low_memorability_content(self, tmp_path: Path) -> None:
        """Short, no error, change type -> low score."""
        scorer, store = _make_scorer(tmp_path, seed_data=True)
        score = scorer.score(
            "ok",
            has_error=False,
            observation_type="change",
        )
        assert score < 0.5
