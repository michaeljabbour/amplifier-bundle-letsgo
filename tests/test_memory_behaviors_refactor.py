"""Tests for Task 3: Refactor Memory Behaviors.

Acceptance Criteria:
1. context/memory-awareness.md is <= 25 lines, contains thin pointer with title,
   one-sentence description, key concepts, safety note, and delegate line to memory-curator.
2. context/memory-system-awareness.md is <= 30 lines, contains thin pointer with
   tool operation names, automation summary, and delegate line.
3. context/memory-store-awareness.md is <= 30 lines, contains thin pointer with
   operation list, key facts, and delegate line.
4. agents/memory-curator.md has @mentions for @letsgo:context/memory-system-awareness.md
   and @letsgo:docs/MEMORY_SYSTEM_GUIDE.md in its Knowledge Base section.
5. docs/MEMORY_SYSTEM_GUIDE.md exists with complete operation descriptions, scoring
   weights, metadata fields, FTS5 details, TTL details, and eviction rules.
6. skills/memory-guide/SKILL.md exists with frontmatter (name, version, description)
   and complete memory system reference documentation.
7. Total of all three memory awareness files <= 90 lines (was 221).
"""

import os
import re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMORY_AWARENESS = os.path.join(REPO_ROOT, "context", "memory-awareness.md")
MEMORY_SYSTEM_AWARENESS = os.path.join(REPO_ROOT, "context", "memory-system-awareness.md")
MEMORY_STORE_AWARENESS = os.path.join(REPO_ROOT, "context", "memory-store-awareness.md")
MEMORY_CURATOR = os.path.join(REPO_ROOT, "agents", "memory-curator.md")
MEMORY_SYSTEM_GUIDE = os.path.join(REPO_ROOT, "docs", "MEMORY_SYSTEM_GUIDE.md")
MEMORY_GUIDE_SKILL = os.path.join(REPO_ROOT, "skills", "memory-guide", "SKILL.md")


def _read(path):
    with open(path) as f:
        return f.read()


def _line_count(path):
    with open(path) as f:
        return len(f.readlines())


# ============================================================
# AC-1: memory-awareness.md is thin pointer (<= 25 lines)
# ============================================================


class TestMemoryAwareness:
    def test_line_count_le_25(self):
        """AC-1: memory-awareness.md is <= 25 lines."""
        count = _line_count(MEMORY_AWARENESS)
        assert count <= 25, f"memory-awareness.md should be <= 25 lines, got {count}"

    def test_has_title(self):
        """AC-1: Has 'Memory Injection' title."""
        content = _read(MEMORY_AWARENESS)
        assert "# Memory Injection" in content

    def test_has_key_concepts(self):
        """AC-1: Has key concepts: scored retrieval, ephemeral injection, untrusted notes."""
        content = _read(MEMORY_AWARENESS).lower()
        assert "scored" in content or "retrieval" in content
        assert "ephemeral" in content
        assert "untrusted" in content

    def test_has_safety_note(self):
        """AC-1: Has safety note about untrusted notes."""
        content = _read(MEMORY_AWARENESS).lower()
        assert "untrusted notes" in content
        assert "never follow instructions" in content or "never follow" in content

    def test_has_delegate_line(self):
        """AC-1: Has delegate line to memory-curator."""
        content = _read(MEMORY_AWARENESS)
        assert "memory-curator" in content
        assert "delegate" in content.lower()

    def test_no_heavy_docs(self):
        """AC-1: No implementation details (scoring weights, dedup mechanics, TTL details)."""
        content = _read(MEMORY_AWARENESS)
        assert "0.55" not in content, "Should not contain scoring weights"
        assert "How It Works" not in content, "Should not have How It Works section"
        assert "SHA-256" not in content, "Should not have dedup mechanics"


# ============================================================
# AC-2: memory-system-awareness.md is thin pointer (<= 30 lines)
# ============================================================


class TestMemorySystemAwareness:
    def test_line_count_le_30(self):
        """AC-2: memory-system-awareness.md is <= 30 lines."""
        count = _line_count(MEMORY_SYSTEM_AWARENESS)
        assert count <= 30, f"memory-system-awareness.md should be <= 30 lines, got {count}"

    def test_has_title(self):
        """AC-2: Has 'Memory System' title."""
        content = _read(MEMORY_SYSTEM_AWARENESS)
        assert "# Memory System" in content

    def test_has_bio_inspired_description(self):
        """AC-2: Has one sentence about bio-inspired memory."""
        content = _read(MEMORY_SYSTEM_AWARENESS).lower()
        assert "bio-inspired" in content or "durable storage" in content

    def test_has_operation_names(self):
        """AC-2: Has tool operation names in compact list."""
        content = _read(MEMORY_SYSTEM_AWARENESS)
        # Should have operation names but NOT full descriptions
        assert "store_memory" in content or "store" in content.lower()
        assert "search" in content.lower()

    def test_has_automation_summary(self):
        """AC-2: Has one-line automation summary about background hooks."""
        content = _read(MEMORY_SYSTEM_AWARENESS).lower()
        assert "hook" in content
        assert ("capture" in content or "automatic" in content or "background" in content)

    def test_has_delegate_line(self):
        """AC-2: Has delegate line to memory-curator."""
        content = _read(MEMORY_SYSTEM_AWARENESS)
        assert "memory-curator" in content
        assert "delegate" in content.lower()

    def test_no_heavy_docs(self):
        """AC-2: No scoring weight details or temporal scale breakdowns."""
        content = _read(MEMORY_SYSTEM_AWARENESS)
        assert "0.55" not in content, "Should not contain scoring weight 0.55"
        assert "0.20" not in content, "Should not contain scoring weight 0.20"
        assert "0.15" not in content, "Should not contain scoring weight 0.15"
        assert "0.10" not in content, "Should not contain scoring weight 0.10"


# ============================================================
# AC-3: memory-store-awareness.md is thin pointer (<= 30 lines)
# ============================================================


class TestMemoryStoreAwareness:
    def test_line_count_le_30(self):
        """AC-3: memory-store-awareness.md is <= 30 lines."""
        count = _line_count(MEMORY_STORE_AWARENESS)
        assert count <= 30, f"memory-store-awareness.md should be <= 30 lines, got {count}"

    def test_has_title(self):
        """AC-3: Has 'Memory Store' title."""
        content = _read(MEMORY_STORE_AWARENESS)
        assert "# Memory Store" in content

    def test_has_operation_list(self):
        """AC-3: Has compact list of operation names."""
        content = _read(MEMORY_STORE_AWARENESS).lower()
        operations = [
            "store", "search", "list", "get", "update", "delete",
            "search_by_file", "search_by_concept", "get_timeline",
            "store_fact", "query_facts", "purge_expired", "summarize_old",
        ]
        for op in operations:
            assert op in content, f"Missing operation: {op}"

    def test_has_key_facts(self):
        """AC-3: Has key facts about deduplication, sensitivity, scoring."""
        content = _read(MEMORY_STORE_AWARENESS).lower()
        assert "dedup" in content or "hash" in content
        assert "sensitivity" in content or "gated" in content
        assert "scored" in content or "relevance" in content

    def test_has_delegate_line(self):
        """AC-3: Has delegate line to memory-curator."""
        content = _read(MEMORY_STORE_AWARENESS)
        assert "memory-curator" in content
        assert "delegate" in content.lower()

    def test_no_heavy_docs(self):
        """AC-3: No rich metadata tables, scoring weights, FTS5 internals."""
        content = _read(MEMORY_STORE_AWARENESS)
        assert "0.55" not in content, "Should not contain scoring weight"
        assert "FTS5" not in content, "Should not contain FTS5 internals"
        assert "mutation journal" not in content.lower() or len(content.splitlines()) <= 30


# ============================================================
# AC-4: memory-curator.md has @mentions in Knowledge Base
# ============================================================


class TestMemoryCurator:
    def test_has_system_awareness_mention(self):
        """AC-4: memory-curator.md has @letsgo:context/memory-system-awareness.md."""
        content = _read(MEMORY_CURATOR)
        assert "@letsgo:context/memory-system-awareness.md" in content

    def test_has_memory_system_guide_mention(self):
        """AC-4: memory-curator.md has @letsgo:docs/MEMORY_SYSTEM_GUIDE.md."""
        content = _read(MEMORY_CURATOR)
        assert "@letsgo:docs/MEMORY_SYSTEM_GUIDE.md" in content

    def test_mentions_in_knowledge_base_section(self):
        """AC-4: Both @mentions are in the Knowledge Base section."""
        content = _read(MEMORY_CURATOR)
        # Find Knowledge Base section
        kb_match = re.search(r"## Knowledge Base\s*\n(.*?)(?=\n## |\Z)", content, re.DOTALL)
        assert kb_match, "Missing '## Knowledge Base' section"
        kb_section = kb_match.group(1)
        assert "@letsgo:context/memory-system-awareness.md" in kb_section
        assert "@letsgo:docs/MEMORY_SYSTEM_GUIDE.md" in kb_section


# ============================================================
# AC-5: docs/MEMORY_SYSTEM_GUIDE.md exists with heavy docs
# ============================================================


class TestMemorySystemGuide:
    def test_file_exists(self):
        """AC-5: docs/MEMORY_SYSTEM_GUIDE.md exists."""
        assert os.path.isfile(MEMORY_SYSTEM_GUIDE), (
            f"{MEMORY_SYSTEM_GUIDE} does not exist"
        )

    def test_has_scoring_weights(self):
        """AC-5: Contains scoring weight breakdown."""
        content = _read(MEMORY_SYSTEM_GUIDE)
        assert "0.55" in content, "Missing match quality weight 0.55"
        assert "0.20" in content, "Missing recency weight 0.20"
        assert "0.15" in content, "Missing importance weight 0.15"
        assert "0.10" in content, "Missing trust weight 0.10"

    def test_has_operation_descriptions(self):
        """AC-5: Contains complete operation descriptions."""
        content = _read(MEMORY_SYSTEM_GUIDE).lower()
        assert "store_memory" in content
        assert "search_memories" in content
        assert "purge_expired" in content
        assert "summarize_old" in content

    def test_has_metadata_fields(self):
        """AC-5: Contains metadata field information."""
        content = _read(MEMORY_SYSTEM_GUIDE).lower()
        assert "title" in content
        assert "subtitle" in content
        assert "concepts" in content
        assert "sensitivity" in content

    def test_has_fts5_details(self):
        """AC-5: Contains FTS5 details."""
        content = _read(MEMORY_SYSTEM_GUIDE)
        assert "FTS5" in content

    def test_has_ttl_details(self):
        """AC-5: Contains TTL and expiry details."""
        content = _read(MEMORY_SYSTEM_GUIDE).lower()
        assert "ttl" in content
        assert "expir" in content  # expired/expiry/expiration

    def test_has_eviction_rules(self):
        """AC-5: Contains eviction priority rules."""
        content = _read(MEMORY_SYSTEM_GUIDE).lower()
        assert "eviction" in content or "evict" in content


# ============================================================
# AC-6: skills/memory-guide/SKILL.md exists with frontmatter
# ============================================================


class TestMemoryGuideSkill:
    def test_file_exists(self):
        """AC-6: skills/memory-guide/SKILL.md exists."""
        assert os.path.isfile(MEMORY_GUIDE_SKILL), (
            f"{MEMORY_GUIDE_SKILL} does not exist"
        )

    def test_has_frontmatter_name(self):
        """AC-6: Frontmatter has name field."""
        content = _read(MEMORY_GUIDE_SKILL)
        assert "name: memory-guide" in content

    def test_has_frontmatter_version(self):
        """AC-6: Frontmatter has version field."""
        content = _read(MEMORY_GUIDE_SKILL)
        assert "version: 1.0.0" in content

    def test_has_frontmatter_description(self):
        """AC-6: Frontmatter has description field."""
        content = _read(MEMORY_GUIDE_SKILL)
        assert "description:" in content

    def test_has_yaml_frontmatter_delimiters(self):
        """AC-6: Has proper YAML frontmatter delimiters."""
        content = _read(MEMORY_GUIDE_SKILL)
        assert content.startswith("---\n")
        # Second --- delimiter after frontmatter
        parts = content.split("---")
        assert len(parts) >= 3, "Missing frontmatter closing delimiter"

    def test_has_substantial_content(self):
        """AC-6: Has complete memory system reference (not just a stub)."""
        count = _line_count(MEMORY_GUIDE_SKILL)
        assert count >= 50, f"Skill should have substantial content, got {count} lines"


# ============================================================
# AC-7: Total of all three awareness files <= 90 lines
# ============================================================


class TestTotalLineCounts:
    def test_total_le_90(self):
        """AC-7: Total of all three memory awareness files <= 90 lines."""
        total = (
            _line_count(MEMORY_AWARENESS)
            + _line_count(MEMORY_SYSTEM_AWARENESS)
            + _line_count(MEMORY_STORE_AWARENESS)
        )
        assert total <= 90, (
            f"Total memory awareness lines should be <= 90, got {total}"
        )
