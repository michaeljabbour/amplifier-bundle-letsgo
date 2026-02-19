"""Auto-capture hook for memory observations from tool executions.

Hooks into tool:post to automatically extract and store observations,
session:start to initialize tracking, and session:end to create summaries.

Merged from amplifier-module-hooks-memory-capture, adapted for letsgo MemoryStore API.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

__amplifier_module_type__ = "hook"


@dataclass
class SessionContext:
    """Per-session tracking state."""

    session_id: str
    project: str | None = None
    user_prompt: str | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    files_read: set[str] = field(default_factory=set)
    files_modified: set[str] = field(default_factory=set)
    observation_count: int = 0
    tools_used: list[str] = field(default_factory=list)


class MemoryCaptureHook:
    """Automatically captures observations from tool executions as memories."""

    FILE_READ_TOOLS = {"read", "read_file", "view", "cat", "Read", "View"}
    FILE_WRITE_TOOLS = {
        "write",
        "write_file",
        "edit",
        "edit_file",
        "str_replace",
        "Edit",
        "Write",
        "MultiEdit",
        "apply_patch",
    }
    LEARNABLE_TOOLS = {
        "bash",
        "read",
        "read_file",
        "grep",
        "glob",
        "search",
        "web_fetch",
        "web_search",
        "LSP",
        "python_check",
        "write",
        "write_file",
        "edit",
        "edit_file",
        "apply_patch",
    }

    BUGFIX_PATTERNS = [
        re.compile(r"\b(fix|fixed|bug|error|crash|exception|traceback)\b", re.I),
        re.compile(r"\b(resolved|patch|hotfix|workaround)\b", re.I),
    ]
    FEATURE_PATTERNS = [
        re.compile(r"\b(add|added|implement|create|new feature)\b", re.I),
        re.compile(r"\b(introduce|support|enable)\b", re.I),
    ]
    DISCOVERY_PATTERNS = [
        re.compile(r"\b(found|discovered|learned|noticed|realized)\b", re.I),
        re.compile(r"\b(turns out|apparently|interesting|unexpected)\b", re.I),
    ]
    REFACTOR_PATTERNS = [
        re.compile(
            r"\b(refactor|rename|restructure|reorganize|cleanup|clean up)\b", re.I
        ),
        re.compile(r"\b(extract|simplify|consolidate|deduplicate)\b", re.I),
    ]

    def __init__(
        self,
        store: Any,
        coordinator: Any,
        *,
        min_content_length: int = 50,
        auto_summarize_interval: int = 10,
    ) -> None:
        self._store = store
        self._coordinator = coordinator
        self._min_content_length = min_content_length
        self._auto_summarize_interval = auto_summarize_interval
        self._sessions: dict[str, SessionContext] = {}

    @property
    def name(self) -> str:
        return "memory_capture"

    @property
    def triggers(self) -> list[tuple[str, int]]:
        return [
            ("tool:post", 150),
            ("session:start", 50),
            ("session:end", 100),
        ]

    async def execute(self, event: str, data: dict[str, Any]) -> dict[str, Any]:
        """Main hook dispatcher."""
        try:
            if event == "session:start":
                return await self._handle_session_start(data)
            elif event == "session:end":
                return await self._handle_session_end(data)
            elif event == "tool:post":
                return await self._handle_tool_post(data)
        except Exception as e:
            logger.debug("Memory capture error (non-blocking): %s", e)
        return {"action": "continue"}

    async def _handle_session_start(self, data: dict[str, Any]) -> dict[str, Any]:
        session_id = data.get("session_id", "default")
        project = self._detect_project(data)
        user_prompt = data.get("user_prompt", "")
        self._sessions[session_id] = SessionContext(
            session_id=session_id,
            project=project,
            user_prompt=user_prompt,
        )
        return {"action": "continue"}

    async def _handle_session_end(self, data: dict[str, Any]) -> dict[str, Any]:
        session_id = data.get("session_id", "default")
        session = self._sessions.pop(session_id, None)
        if session and session.observation_count > 0:
            self._create_session_summary(session)
        return {"action": "continue"}

    async def _handle_tool_post(self, data: dict[str, Any]) -> dict[str, Any]:
        session_id = data.get("session_id", "default")
        session = self._sessions.get(session_id)
        if session is None:
            session = SessionContext(
                session_id=session_id, project=self._detect_project(data)
            )
            self._sessions[session_id] = session

        tool_name = data.get("tool_name", "")
        tool_input = data.get("tool_input", {})
        tool_output = data.get("result", {})

        session.tools_used.append(tool_name)
        self._track_file_operations(session, tool_name, tool_input, tool_output)

        if not self._should_capture(tool_name, tool_output):
            return {"action": "continue"}

        content = self._extract_content(tool_output)
        if not content or len(content) < self._min_content_length:
            return {"action": "continue"}

        obs_type = self._classify_observation_type(tool_name, tool_input, content)
        title = self._generate_title(tool_name, tool_input)
        subtitle = self._generate_subtitle(content)
        importance = self._calculate_importance(obs_type, content)
        concepts = self._determine_concepts(obs_type, tool_name, content)

        stored = self._store_observation(
            session,
            content,
            obs_type,
            title,
            subtitle,
            concepts,
            importance,
        )
        if stored:
            session.observation_count += 1

            if (
                self._auto_summarize_interval > 0
                and session.observation_count % self._auto_summarize_interval == 0
            ):
                self._create_interim_summary(session)

        return {"action": "continue"}

    def _store_observation(
        self,
        session: SessionContext,
        content: str,
        obs_type: str,
        title: str,
        subtitle: str,
        concepts: list[str],
        importance: float,
    ) -> str | None:
        """Store observation via store.store(), optionally gated by memorability."""
        # Check memorability scorer if available
        scorer = self._coordinator.get_capability("memory.memorability")
        if scorer:
            try:
                score = scorer.score(
                    content,
                    tool_name=session.tools_used[-1] if session.tools_used else "",
                    observation_type=obs_type,
                    has_error="error" in content.lower()
                    or "traceback" in content.lower(),
                    file_count=len(session.files_modified),
                )
                if not scorer.should_store(score):
                    return None
                importance = max(importance, score)
            except Exception as e:
                logger.debug("Memorability scoring failed: %s", e)

        try:
            memory_id = self._store.store(
                content=content[:2000],
                type=obs_type,
                title=title,
                subtitle=subtitle,
                concepts=concepts,
                importance=importance,
                files_read=list(session.files_read),
                files_modified=list(session.files_modified),
                session_id=session.session_id,
                project=session.project,
            )
            # Extract and store facts
            facts = self._extract_facts(content)
            for fact_text in facts:
                try:
                    self._store.store_fact(
                        subject=title or "observation",
                        predicate="contains",
                        object_value=fact_text,
                        source_entry_id=memory_id,
                    )
                except Exception:
                    pass
            return memory_id
        except Exception as e:
            logger.debug("Failed to store observation: %s", e)
            return None

    def _should_capture(self, tool_name: str, tool_output: Any) -> bool:
        base_name = tool_name.split(".")[-1] if "." in tool_name else tool_name
        return base_name in self.LEARNABLE_TOOLS

    def _extract_content(self, tool_output: Any) -> str:
        if isinstance(tool_output, str):
            return tool_output
        if isinstance(tool_output, dict):
            for key in ("output", "content", "text", "result", "stdout"):
                if key in tool_output and tool_output[key]:
                    val = tool_output[key]
                    return val if isinstance(val, str) else str(val)
            return str(tool_output)
        return str(tool_output) if tool_output else ""

    def _classify_observation_type(
        self, tool_name: str, tool_input: dict, content: str
    ) -> str:
        text = f"{json.dumps(tool_input)} {content[:500]}"
        if any(p.search(text) for p in self.BUGFIX_PATTERNS):
            return "bugfix"
        if any(p.search(text) for p in self.FEATURE_PATTERNS):
            return "feature"
        if any(p.search(text) for p in self.REFACTOR_PATTERNS):
            return "refactor"
        base = tool_name.split(".")[-1] if "." in tool_name else tool_name
        if base in self.FILE_READ_TOOLS:
            return "discovery"
        if base in self.FILE_WRITE_TOOLS:
            return "change"
        if any(p.search(text) for p in self.DISCOVERY_PATTERNS):
            return "discovery"
        return "change"

    def _generate_title(self, tool_name: str, tool_input: dict) -> str:
        if isinstance(tool_input, dict):
            for key in ("file_path", "path", "file", "command", "pattern", "query"):
                if key in tool_input and tool_input[key]:
                    val = str(tool_input[key])
                    return f"{tool_name}: {val[:80]}"
        return f"{tool_name} observation"

    def _generate_subtitle(self, content: str) -> str:
        first_line = content.strip().split("\n")[0]
        return first_line[:100]

    def _calculate_importance(self, obs_type: str, content: str) -> float:
        type_weights = {
            "bugfix": 0.8,
            "discovery": 0.7,
            "decision": 0.75,
            "feature": 0.6,
            "refactor": 0.5,
            "change": 0.35,
        }
        base = type_weights.get(obs_type, 0.4)
        if len(content) > 500:
            base = min(1.0, base + 0.1)
        return base

    def _determine_concepts(
        self, obs_type: str, tool_name: str, content: str
    ) -> list[str]:
        concepts = []
        type_concept_map = {
            "bugfix": "problem-solution",
            "discovery": "how-it-works",
            "decision": "trade-off",
            "feature": "what-changed",
            "refactor": "what-changed",
            "change": "what-changed",
        }
        if obs_type in type_concept_map:
            concepts.append(type_concept_map[obs_type])
        lower = content.lower()
        if "gotcha" in lower or "caveat" in lower or "watch out" in lower:
            concepts.append("gotcha")
        if "pattern" in lower or "convention" in lower:
            concepts.append("pattern")
        if "because" in lower or "reason" in lower or "why" in lower:
            concepts.append("why-it-exists")
        return concepts[:3]

    def _extract_facts(self, content: str) -> list[str]:
        lines = content.strip().split("\n")
        facts = []
        for line in lines:
            line = line.strip()
            if (
                len(line) > 20
                and len(line) < 200
                and not line.startswith(("#", "//", "/*", "```", "    "))
                and not re.match(r"^\d+[:\s]", line)
            ):
                facts.append(line)
            if len(facts) >= 5:
                break
        return facts

    def _track_file_operations(
        self,
        session: SessionContext,
        tool_name: str,
        tool_input: dict,
        tool_output: Any,
    ) -> None:
        base = tool_name.split(".")[-1] if "." in tool_name else tool_name
        file_path = None
        if isinstance(tool_input, dict):
            file_path = (
                tool_input.get("file_path")
                or tool_input.get("path")
                or tool_input.get("file")
            )

        if file_path and isinstance(file_path, str):
            if base in self.FILE_READ_TOOLS:
                session.files_read.add(file_path)
            elif base in self.FILE_WRITE_TOOLS:
                session.files_modified.add(file_path)

        # Parse bash commands for file paths
        if base == "bash" and isinstance(tool_input, dict):
            cmd = tool_input.get("command", "")
            if isinstance(cmd, str):
                for pattern in [r"cat\s+(\S+)", r"less\s+(\S+)", r"head\s+(\S+)"]:
                    for match in re.finditer(pattern, cmd):
                        session.files_read.add(match.group(1))

    def _detect_project(self, data: dict[str, Any]) -> str | None:
        if "project" in data and data["project"]:
            return str(data["project"])
        cwd = data.get("cwd", "")
        if cwd:
            return cwd.rstrip("/").rsplit("/", 1)[-1]
        return None

    def _create_session_summary(self, session: SessionContext) -> str | None:
        summary = (
            f"Session worked on: {session.user_prompt or 'unknown task'}\n"
            f"Tools used: {', '.join(sorted(set(session.tools_used)))}\n"
            f"Files read: {len(session.files_read)}\n"
            f"Files modified: {len(session.files_modified)}\n"
            f"Observations captured: {session.observation_count}"
        )
        try:
            return self._store.store(
                content=summary,
                type="session_summary",
                title=f"Session Summary: {session.session_id[:12]}",
                importance=0.6,
                session_id=session.session_id,
                project=session.project,
                files_read=list(session.files_read),
                files_modified=list(session.files_modified),
            )
        except Exception as e:
            logger.debug("Failed to create session summary: %s", e)
            return None

    def _create_interim_summary(self, session: SessionContext) -> None:
        summary = (
            f"Interim checkpoint ({session.observation_count} observations)\n"
            f"Files touched: {len(session.files_read | session.files_modified)}"
        )
        try:
            self._store.store(
                content=summary,
                type="session_summary",
                title=(
                    f"Checkpoint: {session.session_id[:12]}"
                    f" @{session.observation_count}"
                ),
                importance=0.4,
                session_id=session.session_id,
                project=session.project,
            )
        except Exception:
            pass


async def mount(coordinator: Any, config: dict[str, Any] | None = None) -> None:
    """Mount the memory capture hook."""
    store = coordinator.get_capability("memory.store")
    if store is None:
        logger.warning("memory.store capability not available; capture hook disabled")
        return

    cfg = config or {}
    hook = MemoryCaptureHook(
        store=store,
        coordinator=coordinator,
        min_content_length=cfg.get("min_content_length", 50),
        auto_summarize_interval=cfg.get("auto_summarize_interval", 10),
    )

    for event, priority in hook.triggers:
        coordinator.hooks.register(
            event=event,
            handler=hook.execute,
            priority=priority,
            name=f"memory-capture.{event.replace(':', '_')}",
        )
