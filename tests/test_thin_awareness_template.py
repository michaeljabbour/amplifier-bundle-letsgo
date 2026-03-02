"""Tests for Task 2: Thin Awareness Template and Dedup Fix.

Acceptance Criteria:
1. docs/thin-awareness-template.md exists with exact
   template content (~25-30 lines).
2. behaviors/memory-store.yaml no longer includes
   letsgo:context/memory-system-awareness.md.
3. Only behaviors/memory-inject.yaml references it.
"""

import os
import re

import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_PATH = os.path.join(REPO_ROOT, "docs", "thin-awareness-template.md")
MEMORY_STORE_YAML = os.path.join(REPO_ROOT, "behaviors", "memory-store.yaml")
MEMORY_INJECT_YAML = os.path.join(REPO_ROOT, "behaviors", "memory-inject.yaml")
BEHAVIORS_DIR = os.path.join(REPO_ROOT, "behaviors")


# ---------- AC-1: Template file exists ----------


def test_template_file_exists():
    """AC-1: docs/thin-awareness-template.md exists."""
    assert os.path.isfile(TEMPLATE_PATH), f"{TEMPLATE_PATH} does not exist"


def test_template_line_count():
    """AC-1: Template is ~25-30 lines (concise)."""
    with open(TEMPLATE_PATH) as f:
        lines = f.readlines()
    assert 20 <= len(lines) <= 35, f"Template should be ~25-30 lines, got {len(lines)}"


def test_template_has_required_sections():
    """AC-1: Template has all required sections."""
    with open(TEMPLATE_PATH) as f:
        content = f.read()
    required_sections = [
        "# [Capability Name]",
        "## Key Concepts",
        "## When This Activates",
        "## Delegate to Expert",
        "## What You Should Know",
    ]
    for section in required_sections:
        assert section in content, f"Missing section: {section}"


def test_template_has_placeholder_patterns():
    """AC-1: Template uses bracket placeholders."""
    with open(TEMPLATE_PATH) as f:
        content = f.read()
    placeholders = re.findall(r"\[.*?\]", content)
    assert len(placeholders) >= 10, (
        f"Expected >= 10 bracket placeholders, found {len(placeholders)}"
    )


# ---------- AC-2: memory-store.yaml dedup fix ----------


def test_memory_store_no_system_awareness():
    """AC-2: memory-store.yaml excludes memory-system-awareness."""
    with open(MEMORY_STORE_YAML) as f:
        content = f.read()
    assert "memory-system-awareness" not in content, (
        "memory-store.yaml should NOT include memory-system-awareness.md"
    )


def test_memory_store_yaml_valid():
    """AC-2: memory-store.yaml is still valid YAML."""
    with open(MEMORY_STORE_YAML) as f:
        data = yaml.safe_load(f)
    assert data is not None
    assert "context" in data
    assert "include" in data["context"]


def test_memory_store_still_has_store_awareness():
    """AC-2: memory-store.yaml still has store-awareness."""
    with open(MEMORY_STORE_YAML) as f:
        data = yaml.safe_load(f)
    includes = data["context"]["include"]
    assert any("memory-store-awareness.md" in inc for inc in includes), (
        "memory-store.yaml should still include memory-store-awareness.md"
    )


# ---------- AC-3: Only memory-inject.yaml references it ----------


def test_only_inject_has_system_awareness():
    """AC-3: Only memory-inject.yaml has memory-system-awareness."""
    files_with_ref = []
    for fname in sorted(os.listdir(BEHAVIORS_DIR)):
        if not fname.endswith(".yaml"):
            continue
        fpath = os.path.join(BEHAVIORS_DIR, fname)
        with open(fpath) as f:
            if "memory-system-awareness" in f.read():
                files_with_ref.append(fname)
    assert files_with_ref == ["memory-inject.yaml"], (
        f"Expected only memory-inject.yaml, found: {files_with_ref}"
    )
