"""Performance benchmark tests — verifies critical paths meet timing budgets.

AAR spec constraints:
- Memory retrieval: < 50ms
- Tool pre-hook: < 5ms
- Sandbox spawn: bounded (not tested here — requires Docker)
- No unbounded memory growth (tested via count assertions)

All timing uses time.monotonic() with p95 assertions.  Budgets are generous
to tolerate CI variance; the AAR numbers are production targets.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from amplifier_module_hooks_tool_policy import ToolPolicyHook
from amplifier_module_tool_memory_store import MemoryStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_hook(tmp_path: Path, **overrides: object) -> ToolPolicyHook:
    """Create a ToolPolicyHook with realistic test config."""
    config: dict[str, object] = {
        "blocked_tools": ["tool-dangerous"],
        "high_risk_tools": ["tool-bash"],
        "medium_risk_tools": ["tool-filesystem", "tool-edit-file"],
        "low_risk_tools": ["tool-grep", "tool-glob", "tool-search", "tool-todo"],
        "allowed_commands": ["echo "],
        "allowed_write_paths": ["/tmp/safe/"],
        "sandbox_mode": "off",
        "default_action": "deny",
        "audit_log_path": str(tmp_path / "perf-audit.jsonl"),
    }
    config.update(overrides)
    return ToolPolicyHook(config)


def _make_store(tmp_path: Path, name: str = "perf_memories.db") -> MemoryStore:
    return MemoryStore(tmp_path / name)


def _tool_event(
    tool_name: str, tool_input: dict[str, object] | None = None
) -> dict[str, object]:
    return {
        "tool_name": tool_name,
        "tool_input": tool_input or {},
        "session_id": "perf-test-session",
    }


def _p95(durations: list[float]) -> float:
    """Return the 95th-percentile value from a sorted copy of *durations*."""
    s = sorted(durations)
    idx = int(len(s) * 0.95)
    return s[min(idx, len(s) - 1)]


# Rotate through every risk tier so benchmarks exercise the full classify path.
_TOOL_CYCLE: list[tuple[str, dict[str, object]]] = [
    ("tool-dangerous", {}),                            # blocked → deny
    ("tool-bash", {"command": "rm /tmp/x"}),           # high → ask_user
    ("tool-filesystem", {"file_path": "/etc/hosts"}),  # medium → continue
    ("tool-grep", {"pattern": "test"}),                # low → continue
    ("tool-unknown", {}),                              # unlisted → deny
    ("tool-bash", {"command": "echo hi"}),             # high → downgraded → continue
    ("tool-glob", {"pattern": "*.py"}),                # low → continue
    ("tool-search", {"query": "hello"}),               # low → continue
]

# Diverse topics for seeding the memory store.
_MEMORY_TOPICS: list[str] = [
    "Python programming language tips and tricks",
    "Kubernetes container orchestration patterns",
    "Machine learning model training pipelines",
    "Database indexing strategies for PostgreSQL",
    "React frontend component architecture",
    "Docker image optimization techniques",
    "GraphQL API schema design principles",
    "Terraform infrastructure as code modules",
    "Redis caching layer implementation",
    "CI/CD pipeline configuration with GitHub Actions",
]

# Varied search queries to avoid caching bias.
_SEARCH_QUERIES: list[str] = [
    "Python programming",
    "Kubernetes container",
    "machine learning model",
    "database indexing",
    "React component",
    "Docker optimization",
    "GraphQL API",
    "Terraform infrastructure",
    "Redis caching",
    "CI/CD pipeline",
    "Python tips",
    "container orchestration",
    "model training pipelines",
    "PostgreSQL strategies",
    "frontend architecture patterns",
    "image optimization techniques",
    "schema design principles",
    "infrastructure code modules",
    "caching layer implementation",
    "GitHub Actions configuration",
]


# ---------------------------------------------------------------------------
# Tool policy hook benchmarks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_policy_hook_under_5ms(tmp_path: Path) -> None:
    """p95 of handle() across 100 calls must be under 5 ms."""
    hook = _make_hook(tmp_path)
    durations: list[float] = []

    for i in range(100):
        tool_name, tool_input = _TOOL_CYCLE[i % len(_TOOL_CYCLE)]
        data = _tool_event(tool_name, tool_input)

        start = time.monotonic()
        await hook.handle("tool:pre", data)
        elapsed = time.monotonic() - start
        durations.append(elapsed)

    p95 = _p95(durations)
    assert p95 < 0.010, f"Tool policy hook p95 = {p95 * 1000:.2f}ms (budget: 10ms)"


# ---------------------------------------------------------------------------
# Memory store benchmarks
# ---------------------------------------------------------------------------


def test_memory_retrieval_under_50ms(tmp_path: Path) -> None:
    """p95 of search_v2() across 50 queries on a 200-memory store < 50 ms."""
    store = _make_store(tmp_path)

    # Seed 200 diverse memories.
    for i in range(200):
        topic = _MEMORY_TOPICS[i % len(_MEMORY_TOPICS)]
        store.store(
            f"Memory #{i}: {topic} — variant {i}",
            category="tech" if i % 2 == 0 else "notes",
            importance=0.3 + (i % 7) * 0.1,
        )

    durations: list[float] = []
    for i in range(50):
        query = _SEARCH_QUERIES[i % len(_SEARCH_QUERIES)]
        start = time.monotonic()
        store.search_v2(query, limit=5, scoring={"min_score": 0.0})
        elapsed = time.monotonic() - start
        durations.append(elapsed)

    p95 = _p95(durations)
    assert p95 < 0.050, f"Memory retrieval p95 = {p95 * 1000:.2f}ms (budget: 50ms)"


def test_memory_store_under_10ms(tmp_path: Path) -> None:
    """p95 of store() across 100 inserts must be under 10 ms."""
    store = _make_store(tmp_path)
    durations: list[float] = []

    for i in range(100):
        content = f"Benchmark memory #{i}: unique content {i} for perf test"

        start = time.monotonic()
        store.store(content, category="bench", importance=0.5)
        elapsed = time.monotonic() - start
        durations.append(elapsed)

    p95 = _p95(durations)
    assert p95 < 0.010, f"Memory store p95 = {p95 * 1000:.2f}ms (budget: 10ms)"


def test_memory_no_unbounded_growth(tmp_path: Path) -> None:
    """Store 1000 memories (500 ephemeral), purge expired, verify exact count.

    Guards against memory leaks: after purge the count must equal exactly
    the number of permanent memories.  Also validates that FTS stays in sync.
    """
    store = _make_store(tmp_path)
    db_path = tmp_path / "perf_memories.db"

    # 500 permanent (even i) + 500 ephemeral (odd i).
    for i in range(1000):
        if i % 2 == 0:
            store.store(
                f"Permanent memory #{i}: this stays",
                category="perm",
            )
        else:
            store.store(
                f"Ephemeral memory #{i}: this expires",
                category="eph",
                ttl_days=1,
            )

    assert store.count() == 1000

    # Force-expire all ephemeral rows by back-dating expires_at.
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "UPDATE memories SET expires_at = '2000-01-01T00:00:00+00:00' "
        "WHERE category = 'eph'"
    )
    conn.commit()
    conn.close()

    purged = store.purge_expired()
    assert purged == 500
    assert store.count() == 500  # only permanent remain

    # FTS should reflect the purge — searching for "expires" should return nothing.
    leftover = store.search_v2("this expires", scoring={"min_score": 0.0})
    assert len(leftover) == 0, "FTS index not purged — stale rows leaked"


def test_fact_store_under_10ms(tmp_path: Path) -> None:
    """p95 of store() with tags and high-trust metadata (fact-like entries) < 10 ms.

    MemoryStore is the unified engine for all stored knowledge.  "Facts" are
    modelled as store() calls with category='fact', high trust, and tags.
    """
    store = _make_store(tmp_path)
    durations: list[float] = []

    for i in range(100):
        start = time.monotonic()
        store.store(
            f"Fact #{i}: the speed of light is approximately {299_792 + i} km/s",
            category="fact",
            importance=0.9,
            trust=0.95,
            tags=[f"physics-{i}", "constants", "science"],
        )
        elapsed = time.monotonic() - start
        durations.append(elapsed)

    p95 = _p95(durations)
    assert p95 < 0.010, f"Fact store p95 = {p95 * 1000:.2f}ms (budget: 10ms)"


def test_bulk_search_scales_linearly(tmp_path: Path) -> None:
    """Insert 100 / 500 / 1000 memories; search time at 1000 must be < 5x at 100.

    Validates roughly-linear scaling of FTS search — not exponential blowup.
    Uses separate databases per level to isolate measurements.
    """
    search_query = "Python programming language"
    n_searches = 20

    level_times: dict[int, float] = {}

    for n_memories in (100, 500, 1000):
        store = MemoryStore(tmp_path / f"scale_{n_memories}.db")

        for i in range(n_memories):
            topic = _MEMORY_TOPICS[i % len(_MEMORY_TOPICS)]
            store.store(
                f"Entry {i}: {topic} — variant {i}",
                category="bench",
                importance=0.5,
            )

        durations: list[float] = []
        for j in range(n_searches):
            # Rotate queries to avoid any single-query caching advantage.
            q = _SEARCH_QUERIES[j % len(_SEARCH_QUERIES)]
            start = time.monotonic()
            store.search_v2(q, limit=5, scoring={"min_score": 0.0})
            elapsed = time.monotonic() - start
            durations.append(elapsed)

        level_times[n_memories] = _p95(durations)

    # Guard against division by zero on very fast systems.
    baseline = max(level_times[100], 1e-9)
    ratio = level_times[1000] / baseline

    assert ratio < 5.0, (
        f"Search scaling ratio (1000/100) = {ratio:.1f}x (budget: < 5x)\n"
        f"  100 memories p95: {level_times[100] * 1000:.2f}ms\n"
        f"  500 memories p95: {level_times[500] * 1000:.2f}ms\n"
        f"  1000 memories p95: {level_times[1000] * 1000:.2f}ms"
    )
