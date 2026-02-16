"""Cron scheduler for the gateway."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def parse_cron_expression(expr: str) -> dict[str, Any]:
    """Parse a simple cron expression into a schedule descriptor.

    Supports:
        ``@hourly``   — minute 0 every hour
        ``@daily``    — 00:00 every day
        ``@weekly``   — 00:00 every Monday
        ``MM HH * * *`` — specific minute and hour every day

    Returns a dict with ``minute``, ``hour``, and ``weekday`` (0=Mon, None=any).
    """
    shortcuts: dict[str, dict[str, Any]] = {
        "@hourly": {"minute": 0, "hour": None, "weekday": None},
        "@daily": {"minute": 0, "hour": 0, "weekday": None},
        "@weekly": {"minute": 0, "hour": 0, "weekday": 0},
    }
    if expr in shortcuts:
        return shortcuts[expr]

    parts = expr.strip().split()
    if len(parts) < 5:
        raise ValueError(f"Invalid cron expression: {expr!r}")

    minute = int(parts[0]) if parts[0] != "*" else None
    hour = int(parts[1]) if parts[1] != "*" else None
    weekday = int(parts[4]) if parts[4] != "*" else None

    return {"minute": minute, "hour": hour, "weekday": weekday}


def is_due(schedule: dict[str, Any], now: datetime) -> bool:
    """Return True if *schedule* matches the current time (minute-level)."""
    if schedule.get("minute") is not None and now.minute != schedule["minute"]:
        return False
    if schedule.get("hour") is not None and now.hour != schedule["hour"]:
        return False
    if schedule.get("weekday") is not None and now.weekday() != schedule["weekday"]:
        return False
    return True


def next_run_description(schedule: dict[str, Any]) -> str:
    """Human-readable description of when the job next runs."""
    parts = []
    if schedule.get("weekday") is not None:
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        parts.append(f"every {days[schedule['weekday']]}")
    if schedule.get("hour") is not None:
        parts.append(f"at {schedule['hour']:02d}:{schedule.get('minute', 0):02d}")
    elif schedule.get("minute") is not None:
        parts.append(f"at minute {schedule['minute']:02d} every hour")
    return " ".join(parts) if parts else "every minute"


class CronJob:
    """A single scheduled job."""

    def __init__(
        self,
        name: str,
        cron_expression: str,
        recipe_path: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.name = name
        self.cron_expression = cron_expression
        self.recipe_path = recipe_path
        self.context = context or {}
        self.schedule = parse_cron_expression(cron_expression)
        self.last_run: datetime | None = None


class CronScheduler:
    """Simple cron-like scheduler for gateway recipe jobs."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        config = config or {}
        default_log = Path("~/.letsgo/gateway/cron.jsonl").expanduser()
        self._log_path = Path(config.get("log_path", str(default_log)))
        self._automation_profile: dict[str, Any] = config.get(
            "automation_profile", {}
        )
        self._jobs: dict[str, CronJob] = {}
        self._task: asyncio.Task[None] | None = None
        self._running = False

        # Load initial jobs from config
        for job_def in config.get("jobs", []):
            self.schedule(
                name=job_def["name"],
                cron_expression=job_def["cron"],
                recipe_path=job_def["recipe"],
                context=job_def.get("context"),
            )

    def schedule(
        self,
        name: str,
        cron_expression: str,
        recipe_path: str,
        context: dict[str, Any] | None = None,
    ) -> CronJob:
        """Register a new scheduled job."""
        job = CronJob(
            name=name,
            cron_expression=cron_expression,
            recipe_path=recipe_path,
            context=context,
        )
        self._jobs[name] = job
        logger.info("Scheduled job '%s': %s -> %s", name, cron_expression, recipe_path)
        return job

    def unschedule(self, name: str) -> bool:
        """Remove a job by name. Returns True if it existed."""
        return self._jobs.pop(name, None) is not None

    def list_jobs(self) -> list[dict[str, Any]]:
        """Return info about all registered jobs."""
        result = []
        for job in self._jobs.values():
            result.append({
                "name": job.name,
                "cron": job.cron_expression,
                "recipe": job.recipe_path,
                "context": job.context,
                "next_run": next_run_description(job.schedule),
                "last_run": (
                    job.last_run.isoformat() if job.last_run else None
                ),
            })
        return result

    def get_automation_profile(self) -> dict[str, Any]:
        """Return the automation profile for cron-triggered sessions."""
        return dict(self._automation_profile)

    async def _run_loop(self) -> None:
        """Main scheduler loop — checks jobs every 60 seconds."""
        while self._running:
            now = datetime.now(timezone.utc)
            for job in list(self._jobs.values()):
                if is_due(job.schedule, now):
                    # Avoid running the same minute twice
                    if (
                        job.last_run is not None
                        and job.last_run.minute == now.minute
                        and job.last_run.hour == now.hour
                        and job.last_run.date() == now.date()
                    ):
                        continue
                    job.last_run = now
                    await self._execute_job(job, now)
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                break

    async def _execute_job(self, job: CronJob, now: datetime) -> None:
        """Execute a cron job (stub: logs the execution)."""
        entry = {
            "timestamp": now.isoformat(),
            "job": job.name,
            "recipe": job.recipe_path,
            "context": job.context,
            "automation_profile": self._automation_profile,
            "status": "triggered",
        }
        logger.info("Cron job '%s' triggered at %s", job.name, now.isoformat())
        self._append_log(entry)

    def _append_log(self, entry: dict[str, Any]) -> None:
        """Append a JSONL entry to the cron log."""
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    async def start(self) -> None:
        """Start the scheduler loop."""
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("CronScheduler started with %d jobs", len(self._jobs))

    async def stop(self) -> None:
        """Stop the scheduler loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("CronScheduler stopped")
