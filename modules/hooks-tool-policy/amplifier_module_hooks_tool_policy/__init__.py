"""Tool execution policy hook with risk classification, allowlists, and approval gates.

Intercepts ``tool:pre`` events to enforce a configurable security policy before
any tool executes.  Decisions are based on four risk tiers (blocked / high /
medium / low), two allowlist mechanisms (command-prefix and path-prefix), an
optional sandbox rewrite for bash commands, and a JSONL audit trail.

**Default-deny invariant**: unlisted tools are denied by default.  To allow a
new tool, it must be explicitly added to a risk tier.

Configuration keys (all optional, sane defaults provided)::

    high_risk_tools      - list[str]  (default: ["tool-bash"])
    medium_risk_tools    - list[str]  (default: ["tool-filesystem"])
    low_risk_tools       - list[str]  (default: [])
    blocked_tools        - list[str]  (default: [])
    default_action       - "deny" | "ask_user" | "continue"  (default: "deny")
    allowed_commands     - list[str]  command prefixes that downgrade bash → low
    allowed_write_paths  - list[str]  path prefixes that downgrade fs writes → low
    sandbox_mode         - "enforce" | "off"  (default: "enforce")
    audit_log_path       - str  (default: "~/.letsgo/logs/tool-policy-audit.jsonl")
    automation_mode      - bool  (default: false) restricted profile for scheduled runs
"""

from __future__ import annotations

__amplifier_module_type__ = "hook"

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from amplifier_core.models import HookResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Policy engine
# ---------------------------------------------------------------------------


class ToolPolicyHook:
    """Stateful policy engine instantiated once per mount with frozen config."""

    def __init__(self, config: dict[str, Any]) -> None:
        # Risk classification lists
        self.blocked_tools: list[str] = config.get("blocked_tools", [])
        self.high_risk_tools: list[str] = config.get("high_risk_tools", ["tool-bash"])
        self.medium_risk_tools: list[str] = config.get(
            "medium_risk_tools", ["tool-filesystem"]
        )
        self.low_risk_tools: list[str] = config.get("low_risk_tools", [])

        # Default action for unlisted tools: "deny" | "ask_user" | "continue"
        self.default_action: str = config.get("default_action", "deny")

        # Automation mode — restricted profile for scheduled/unattended runs.
        # When True: secrets tool blocked, all high-risk → deny (no ask_user),
        # unknown tools → deny regardless of default_action.
        self.automation_mode: bool = config.get("automation_mode", False)

        # Allowlists
        self.allowed_commands: list[str] = config.get("allowed_commands", [])
        self.allowed_write_paths: list[str] = config.get("allowed_write_paths", [])

        # Sandbox
        self.sandbox_mode: str = config.get("sandbox_mode", "enforce")

        # Audit
        self.audit_log_path: Path = Path(
            config.get("audit_log_path", "~/.letsgo/logs/tool-policy-audit.jsonl")
        ).expanduser()

        # Build the set of all explicitly classified tools for fast lookup
        self._classified_tools: frozenset[str] = frozenset(
            self.blocked_tools
            + self.high_risk_tools
            + self.medium_risk_tools
            + self.low_risk_tools
        )

    # -- risk classification ------------------------------------------------

    def classify_risk(self, tool_name: str) -> str:
        """Return the base risk tier for *tool_name* from the configured lists.

        Evaluation order is blocked → high → medium → low.  Unlisted tools
        are classified according to ``default_action``: ``"deny"`` maps to
        ``"unclassified"`` (which the handler treats as deny), ``"ask_user"``
        maps to ``"high"``, and ``"continue"`` maps to ``"low"``.

        In **automation mode**, secrets tools are always blocked and unlisted
        tools are always denied regardless of ``default_action``.
        """
        # Automation mode: block secrets tool entirely
        if self.automation_mode and tool_name in ("tool-secrets", "secrets"):
            return "blocked"

        if tool_name in self.blocked_tools:
            return "blocked"
        if tool_name in self.high_risk_tools:
            return "high"
        if tool_name in self.medium_risk_tools:
            return "medium"
        if tool_name in self.low_risk_tools:
            return "low"

        # Unlisted tool — default-deny invariant
        if self.automation_mode:
            return "unclassified"

        if self.default_action == "ask_user":
            return "high"
        if self.default_action == "continue":
            return "low"
        # default_action == "deny" or anything else → unclassified
        return "unclassified"

    # -- allowlist checks ---------------------------------------------------

    @staticmethod
    def _prefix_match(value: str, prefix: str) -> bool:
        """Return ``True`` if *value* starts with *prefix* at a word boundary.

        A word boundary means the character immediately after the prefix is
        a space, path separator, end-of-string, or other non-alphanumeric
        character.  This prevents ``"git"`` from matching ``"gitevil"``.

        When the prefix itself already ends with a non-alphanumeric character
        (e.g. ``"echo "`` with a trailing space), the boundary is built in
        and any continuation is accepted.
        """
        if not value.startswith(prefix):
            return False
        # Exact match — always accept.
        if len(value) == len(prefix):
            return True
        # If the prefix already ends with a non-alnum char (e.g. "echo "),
        # the word boundary is built into the prefix itself.
        if prefix and not prefix[-1].isalnum():
            return True
        # Otherwise require a word boundary after the prefix.
        next_char = value[len(prefix)]
        return not next_char.isalnum() and next_char != "-"

    def _command_matches_allowlist(self, tool_input: dict[str, Any]) -> bool:
        """Return ``True`` if the bash command starts with an allowed prefix.

        Uses word-boundary matching so ``allowed_commands: ["git"]`` matches
        ``"git status"`` but not ``"gitevil --steal"``.
        """
        if not self.allowed_commands:
            return False
        command: str = tool_input.get("command", "")
        return any(self._prefix_match(command, prefix) for prefix in self.allowed_commands)

    def _path_matches_allowlist(self, tool_input: dict[str, Any]) -> bool:
        """Return ``True`` if the target file path falls under an allowed directory.

        Paths are resolved (normalised) before comparison to prevent traversal
        attacks such as ``/tmp/safe/../../etc/passwd``.
        """
        if not self.allowed_write_paths:
            return False
        raw_path: str = tool_input.get("file_path", "") or tool_input.get("path", "")
        if not raw_path:
            return False
        try:
            resolved = os.path.realpath(raw_path)
        except (OSError, ValueError):
            return False
        return any(
            resolved.startswith(os.path.realpath(prefix))
            for prefix in self.allowed_write_paths
        )

    @staticmethod
    def _is_write_operation(tool_input: dict[str, Any]) -> bool:
        """Heuristic: does *tool_input* describe a filesystem write?"""
        if "content" in tool_input:
            return True
        operation = tool_input.get("operation", "").lower()
        return operation in {"write", "create", "delete", "move", "rename"}

    def apply_allowlist_downgrade(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        risk_level: str,
    ) -> str:
        """Downgrade *risk_level* when the operation matches an allowlist.

        * **Command allowlist** – a ``tool-bash`` command whose text starts with
          any entry in ``allowed_commands`` is downgraded from *high → low*.
        * **Path allowlist** – a ``tool-filesystem`` write whose target path
          starts with any entry in ``allowed_write_paths`` is downgraded from
          *medium → low*.
        """
        if risk_level == "high" and tool_name == "tool-bash":
            if self._command_matches_allowlist(tool_input):
                logger.debug(
                    "Allowlist downgrade: %s high → low (command prefix match)",
                    tool_name,
                )
                return "low"

        if risk_level == "medium" and tool_name == "tool-filesystem":
            if self._is_write_operation(tool_input) and self._path_matches_allowlist(
                tool_input
            ):
                logger.debug(
                    "Allowlist downgrade: %s medium → low (path prefix match)",
                    tool_name,
                )
                return "low"

        return risk_level

    # -- sandbox rewrite ----------------------------------------------------

    def build_sandbox_data(self, data: dict[str, Any]) -> dict[str, Any]:
        """Return a *modified* copy of *data* that routes through ``tool-sandbox``.

        The original command is preserved inside ``tool_input`` so that the
        sandbox tool can unwrap and execute it in a restricted environment.
        """
        original_input = data.get("tool_input", {})
        return {
            **data,
            "tool_name": "tool-sandbox",
            "tool_input": {
                "command": original_input.get("command", ""),
                "original_tool": "tool-bash",
                "run_in_background": original_input.get("run_in_background", False),
            },
        }

    # -- audit logging ------------------------------------------------------

    async def write_audit_entry(
        self,
        *,
        session_id: str,
        tool_name: str,
        risk_level: str,
        action: str,
        reason: str,
    ) -> None:
        """Append a single JSON line to the audit log.

        Filesystem errors are caught and logged as warnings so that a broken
        log path never blocks tool execution.
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "tool_name": tool_name,
            "risk_level": risk_level,
            "action": action,
            "reason": reason,
        }
        try:
            self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.audit_log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, separators=(",", ":")) + "\n")
        except OSError:
            logger.warning(
                "Failed to write audit log entry to %s",
                self.audit_log_path,
                exc_info=True,
            )

    # -- main handler -------------------------------------------------------

    async def handle(self, event: str, data: dict[str, Any]) -> HookResult:
        """``tool:pre`` handler — classify, gate, optionally rewrite, and audit.

        Returns a :class:`HookResult` whose *action* is one of:

        * ``"deny"``     – blocked tools
        * ``"ask_user"`` – high-risk tools (not allowlisted)
        * ``"modify"``   – sandbox rewrite for bash commands
        * ``"continue"`` – medium / low risk (medium emits an info message)
        """
        tool_name: str = data.get("tool_name", "")
        tool_input: dict[str, Any] = data.get("tool_input", {})
        session_id: str = data.get("session_id", "unknown")

        # 1. Base risk classification
        risk_level = self.classify_risk(tool_name)

        # 2. Allowlist downgrade (skipped for blocked tools)
        if risk_level not in ("blocked",):
            risk_level = self.apply_allowlist_downgrade(
                tool_name, tool_input, risk_level
            )

        # 3. Map risk level → HookResult
        result: HookResult
        reason: str

        if risk_level == "unclassified":
            reason = (
                f"Tool '{tool_name}' is not in any risk classification — "
                "denied by default-deny policy"
            )
            result = HookResult(action="deny", reason=reason)

        elif risk_level == "blocked":
            reason = f"Tool '{tool_name}' is blocked by security policy"
            result = HookResult(action="deny", reason=reason)

        elif risk_level == "high":
            # In automation mode, high-risk tools are denied outright
            # (no user present to approve).
            if self.automation_mode:
                reason = (
                    f"High-risk tool '{tool_name}' denied — "
                    "automation mode does not permit interactive approval"
                )
                result = HookResult(action="deny", reason=reason)
            else:
                command_preview = (
                    _truncated_command(tool_input)
                    if tool_name == "tool-bash"
                    else ""
                )
                prompt_detail = f": {command_preview}" if command_preview else ""
                reason = f"High-risk tool '{tool_name}' requires user approval"
                result = HookResult(
                    action="ask_user",
                    approval_prompt=(
                        f"Tool '{tool_name}' is classified as HIGH risk"
                        f"{prompt_detail}.\nAllow this operation?"
                    ),
                    approval_timeout=120.0,
                    approval_default="deny",
                )

        elif risk_level == "medium":
            summary = _summarize_operation(tool_name, tool_input)
            reason = f"Medium-risk tool '{tool_name}' — auto-proceed"
            result = HookResult(
                action="continue",
                user_message=f"[tool-policy] {summary}",
                user_message_level="info",
                user_message_source="hooks-tool-policy",
            )

        else:  # low (including allowlisted downgrades)
            reason = f"Low-risk tool '{tool_name}' — proceed"
            result = HookResult(action="continue")

        # 4. Sandbox rewrite (non-blocked, non-ask_user bash calls only)
        if (
            self.sandbox_mode == "enforce"
            and tool_name == "tool-bash"
            and result.action not in ("deny", "ask_user")
        ):
            sandbox_data = self.build_sandbox_data(data)
            reason = f"Sandbox rewrite: {tool_name} → tool-sandbox"
            result = HookResult(
                action="modify",
                data=sandbox_data,
                reason=reason,
                # Preserve any informational user_message from the risk tier
                user_message=result.user_message,
                user_message_level=result.user_message_level,
            )

        # 5. Audit trail
        await self.write_audit_entry(
            session_id=session_id,
            tool_name=tool_name,
            risk_level=risk_level,
            action=result.action,
            reason=reason,
        )

        return result


# ---------------------------------------------------------------------------
# Helpers (module-private)
# ---------------------------------------------------------------------------


def _truncated_command(tool_input: dict[str, Any], max_len: int = 80) -> str:
    """Return a display-safe snippet of a bash command."""
    cmd: str = tool_input.get("command", "")
    if len(cmd) <= max_len:
        return cmd
    return cmd[:max_len] + "…"


def _summarize_operation(tool_name: str, tool_input: dict[str, Any]) -> str:
    """Build a short human-readable description for info-level messages."""
    if tool_name == "tool-filesystem":
        path = tool_input.get("file_path", "") or tool_input.get("path", "unknown")
        if "content" in tool_input:
            return f"Filesystem write → {path}"
        return f"Filesystem operation → {path}"
    if tool_name == "tool-bash":
        return f"Bash → {_truncated_command(tool_input, 60)}"
    return f"Tool execution → {tool_name}"


# ---------------------------------------------------------------------------
# Module entry point
# ---------------------------------------------------------------------------


async def mount(coordinator, config=None):  # noqa: ANN001
    """Mount the tool-policy hook on the coordinator's hook registry.

    Args:
        coordinator: The :class:`ModuleCoordinator` provided by the kernel.
        config: Optional dict of policy settings (risk lists, allowlists,
                sandbox mode, audit path).  See module docstring for keys.

    Returns:
        A cleanup callable that unregisters the hook handler.
    """
    config = config or {}
    hook = ToolPolicyHook(config)

    unregister = coordinator.hooks.register(
        "tool:pre",
        hook.handle,
        priority=5,
        name="hooks-tool-policy",
    )

    logger.info(
        "hooks-tool-policy mounted  sandbox=%s  default=%s  automation=%s  "
        "blocked=%s  high=%s  medium=%s",
        hook.sandbox_mode,
        hook.default_action,
        hook.automation_mode,
        hook.blocked_tools,
        hook.high_risk_tools,
        hook.medium_risk_tools,
    )

    def cleanup():
        unregister()
        logger.info("hooks-tool-policy unmounted")

    return cleanup
