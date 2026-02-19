"""Heartbeat engine — proactive session execution on a schedule.

The heartbeat transforms the system from reactive (responds to user messages)
to proactive (checks in on a schedule, reviews memory, surfaces pending work).

Architecture:
    CronScheduler fires → HeartbeatEngine.run() → for each agent:
        1. Build prompt from context/ files (system + per-agent focus)
        2. Create Amplifier session via session_factory callback
        3. Execute prompt in session (memory hooks fire automatically)
        4. Route response to designated channels
        5. Log heartbeat result

This follows the "Headless Session" pattern: sessions don't know or care
what triggered them. A heartbeat session is identical to a user-triggered
session — all hooks fire, all tools are available, all context loads.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

# Type alias for the session factory callback
# (agent_id, prompt, workspace_path) -> response string
SessionExecutor = Callable[[str, str, Path], Awaitable[str]]

# Type alias for the response router callback
# (agent_id, response, channels) -> None
ResponseRouter = Callable[[str, str, list[str]], Awaitable[None]]


class HeartbeatEngine:
    """Proactive heartbeat engine for the letsgo gateway.

    The engine is NOT a recipe, NOT a hook, NOT a standalone module.
    It's app-layer policy code that uses Amplifier's session mechanism.

    The CronScheduler owns the "when" (scheduling policy).
    The HeartbeatEngine owns the "what" (prompt construction + session execution).
    The PreparedBundle owns the "how" (session creation mechanism).
    """

    def __init__(
        self,
        *,
        session_executor: SessionExecutor | None = None,
        response_router: ResponseRouter | None = None,
        context_dir: Path | None = None,
        agents_config: dict[str, dict[str, Any]] | None = None,
        default_channels: list[str] | None = None,
    ) -> None:
        self._session_executor = session_executor
        self._response_router = response_router
        self._context_dir = context_dir or Path(__file__).parent.parent.parent / "context" / "heartbeat"
        self._agents_config = agents_config or {}
        self._default_channels = default_channels or []
        self._history: list[dict[str, Any]] = []

    # ---- Prompt Construction ----

    def _load_context_file(self, path: Path) -> str | None:
        """Load a context file, returning None if it doesn't exist."""
        if path.exists():
            return path.read_text().strip()
        return None

    def build_prompt(self, agent_id: str) -> str:
        """Construct the heartbeat prompt for a specific agent.

        Loads:
        1. Shared system instructions (context/heartbeat/heartbeat-system.md)
        2. Per-agent focus (context/heartbeat/agents/{agent_id}.md)
        3. Falls back to default (context/heartbeat/agents/default.md)
        """
        # Shared system instructions
        system = self._load_context_file(
            self._context_dir / "heartbeat-system.md"
        )

        # Per-agent focus (or default)
        agent_focus = (
            self._load_context_file(self._context_dir / "agents" / f"{agent_id}.md")
            or self._load_context_file(self._context_dir / "agents" / "default.md")
        )

        parts = []
        if system:
            parts.append(system)
        if agent_focus:
            parts.append(f"## Your Focus\n\n{agent_focus}")

        if not parts:
            # Absolute fallback — no context files found
            return (
                "Heartbeat check-in. Review your recent memory for pending tasks, "
                "unresolved issues, or important context. Respond with a brief "
                "status update (2-3 sentences max)."
            )

        return "\n\n".join(parts)

    # ---- Execution ----

    async def run_heartbeat(self, agent_id: str) -> dict[str, Any]:
        """Execute a single heartbeat for one agent.

        Returns a result dict with status, response, and timing.
        """
        start = time.monotonic()
        result: dict[str, Any] = {
            "agent_id": agent_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "pending",
        }

        try:
            prompt = self.build_prompt(agent_id)
            result["prompt_length"] = len(prompt)

            if self._session_executor is None:
                result["status"] = "skipped"
                result["reason"] = "no session_executor configured"
                logger.warning(
                    "Heartbeat for '%s' skipped: no session_executor", agent_id
                )
                return result

            # Determine workspace for this agent
            agent_config = self._agents_config.get(agent_id, {})
            workspace = Path(
                agent_config.get(
                    "workspace",
                    f"~/.letsgo/agents/{agent_id}"
                )
            ).expanduser()
            workspace.mkdir(parents=True, exist_ok=True)

            # Execute the heartbeat session
            response = await self._session_executor(agent_id, prompt, workspace)
            result["status"] = "completed"
            result["response"] = response
            result["response_length"] = len(response) if response else 0

            # Route response to channels if configured
            channels = agent_config.get("heartbeat_channels", self._default_channels)
            if channels and response and self._response_router:
                try:
                    await self._response_router(agent_id, response, channels)
                    result["routed_to"] = channels
                except Exception as e:
                    result["routing_error"] = str(e)
                    logger.exception(
                        "Failed to route heartbeat response for '%s'", agent_id
                    )

        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
            logger.exception("Heartbeat failed for agent '%s'", agent_id)

        result["duration_ms"] = int((time.monotonic() - start) * 1000)
        self._history.append(result)
        return result

    async def run_all(self) -> list[dict[str, Any]]:
        """Execute heartbeats for ALL configured agents.

        This is the callback the CronScheduler invokes.
        """
        agent_ids = list(self._agents_config.keys())
        if not agent_ids:
            logger.info("No agents configured for heartbeat")
            return []

        logger.info("Running heartbeat for %d agents: %s", len(agent_ids), agent_ids)
        results = []
        for agent_id in agent_ids:
            result = await self.run_heartbeat(agent_id)
            results.append(result)
            logger.info(
                "Heartbeat '%s': %s (%dms)",
                agent_id,
                result["status"],
                result.get("duration_ms", 0),
            )

        return results

    # ---- Introspection ----

    @property
    def history(self) -> list[dict[str, Any]]:
        """Return heartbeat execution history (most recent last)."""
        return list(self._history)

    def last_result(self, agent_id: str) -> dict[str, Any] | None:
        """Return the most recent heartbeat result for an agent."""
        for entry in reversed(self._history):
            if entry["agent_id"] == agent_id:
                return entry
        return None
