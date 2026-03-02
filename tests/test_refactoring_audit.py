"""Tests for docs/refactoring-audit.md - verifies the audit document
meets all acceptance criteria for Task 1: Repository Setup and Audit."""

import os
import subprocess

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIT_PATH = os.path.join(REPO_ROOT, "docs", "refactoring-audit.md")


# ---------- AC-1: Feature branch exists ----------

def test_feature_branch_exists():
    """AC-1: Feature branch feat/thin-behaviors exists."""
    result = subprocess.run(
        ["git", "branch", "--list", "feat/thin-behaviors"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert "feat/thin-behaviors" in result.stdout, (
        "Branch feat/thin-behaviors does not exist"
    )


# ---------- AC-2: Audit document exists ----------

def test_audit_file_exists():
    """AC-2: docs/refactoring-audit.md exists."""
    assert os.path.isfile(AUDIT_PATH), f"{AUDIT_PATH} does not exist"


# ---------- helpers ----------

EXPECTED_CONTEXT_FILES = [
    "browser-awareness.md",
    "canvas-awareness.md",
    "gateway-awareness.md",
    "heartbeat-awareness.md",
    "heartbeat-system.md",
    "letsgo-instructions.md",
    "mcp-awareness.md",
    "memory-awareness.md",
    "memory-store-awareness.md",
    "memory-system-awareness.md",
    "observability-awareness.md",
    "sandbox-awareness.md",
    "secrets-awareness.md",
    "skills-awareness.md",
    "soul-framework-awareness.md",
    "team-collaboration-awareness.md",
    "tool-policy-awareness.md",
    "voice-awareness.md",
    "webchat-awareness.md",
]

EXPECTED_AGENTS = [
    "admin-assistant",
    "creative-specialist",
    "document-specialist",
    "gateway-operator",
    "mcp-specialist",
    "memory-curator",
    "security-reviewer",
    "voice-specialist",
]


def _read_audit():
    with open(AUDIT_PATH) as f:
        return f.read()


def _is_table_data_row(line):
    """True if line is a markdown table data row (not header/separator)."""
    return "|" in line and "---" not in line


# ---------- AC-2: Awareness files table ----------

def test_awareness_table_has_all_files():
    """AC-2: Awareness files table lists all context files."""
    content = _read_audit()
    for fname in EXPECTED_CONTEXT_FILES:
        assert fname in content, f"Missing context file in audit: {fname}"


def test_awareness_table_row_count():
    """AC-2: Awareness files table has at least 17 rows."""
    content = _read_audit()
    context_rows = [
        line for line in content.splitlines()
        if _is_table_data_row(line)
        and any(f in line for f in EXPECTED_CONTEXT_FILES)
    ]
    assert len(context_rows) >= 17, (
        f"Expected at least 17 awareness-file rows, found {len(context_rows)}"
    )


# ---------- AC-2: Agents table has 8 agents ----------

def test_agents_table_has_all_agents():
    """AC-2: Agents table lists all 8 agent files."""
    content = _read_audit()
    for agent in EXPECTED_AGENTS:
        assert agent in content, f"Missing agent in audit: {agent}"


def test_agents_table_row_count():
    """AC-2: Agents table has 8 agent rows."""
    content = _read_audit()
    # Agent rows start with "| <agent-name>" as the first column
    # and do NOT contain ".md" (which would be awareness table rows)
    agent_rows = [
        line for line in content.splitlines()
        if _is_table_data_row(line)
        and any(f"| {a} " in line or f"| {a} |" in line for a in EXPECTED_AGENTS)
        and ".md" not in line
    ]
    assert len(agent_rows) == 8, (
        f"Expected 8 agent rows, found {len(agent_rows)}: {agent_rows}"
    )


# ---------- AC-2: Status columns all 'pending' ----------

def test_all_status_pending():
    """AC-2: All Status columns are set to 'pending'."""
    content = _read_audit()
    # Collect all data rows from both tables
    table_rows = [
        line for line in content.splitlines()
        if _is_table_data_row(line)
        and (
            any(f in line for f in EXPECTED_CONTEXT_FILES)
            or any(f"| {a} " in line for a in EXPECTED_AGENTS)
        )
        and "Status" not in line
    ]
    assert len(table_rows) > 0, "No table rows found"
    for row in table_rows:
        assert "pending" in row.lower(), f"Row not 'pending': {row}"


# ---------- AC-2: Target metrics section ----------

def test_target_metrics_section():
    """AC-2: Audit contains target metrics (before vs after)."""
    content = _read_audit()
    assert "target" in content.lower() or "metric" in content.lower(), (
        "Missing target metrics section"
    )
    assert "1273" in content, "Missing total context lines before count (1273)"


# ---------- AC-2: Completed section ----------

def test_completed_section_exists():
    """AC-2: Audit has a Completed section for tracking progress."""
    content = _read_audit()
    assert "## completed" in content.lower() or "## progress" in content.lower(), (
        "Missing Completed/Progress section"
    )
