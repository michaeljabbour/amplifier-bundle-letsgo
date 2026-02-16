"""Tests for gateway cron scheduler."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from letsgo_gateway.cron import (
    CronJob,
    CronScheduler,
    is_due,
    parse_cron_expression,
)


# ---------------------------------------------------------------------------
# Cron expression parsing
# ---------------------------------------------------------------------------


def test_cron_expression_parsing():
    """Standard shortcuts and MM HH format are parsed correctly."""
    hourly = parse_cron_expression("@hourly")
    assert hourly == {"minute": 0, "hour": None, "weekday": None}

    daily = parse_cron_expression("@daily")
    assert daily == {"minute": 0, "hour": 0, "weekday": None}

    weekly = parse_cron_expression("@weekly")
    assert weekly == {"minute": 0, "hour": 0, "weekday": 0}

    custom = parse_cron_expression("30 14 * * *")
    assert custom == {"minute": 30, "hour": 14, "weekday": None}


def test_cron_expression_invalid():
    """Invalid expressions raise ValueError."""
    with pytest.raises(ValueError, match="Invalid cron"):
        parse_cron_expression("bad")


# ---------------------------------------------------------------------------
# Job scheduling
# ---------------------------------------------------------------------------


def test_schedule_and_list_jobs(tmp_path):
    """Scheduling a job makes it appear in list_jobs."""
    sched = CronScheduler({"log_path": str(tmp_path / "cron.jsonl")})
    sched.schedule("nightly", "@daily", "recipes/backup.yaml", {"db": "main"})
    sched.schedule("hourly-check", "@hourly", "recipes/check.yaml")

    jobs = sched.list_jobs()
    assert len(jobs) == 2
    names = {j["name"] for j in jobs}
    assert names == {"nightly", "hourly-check"}

    nightly = next(j for j in jobs if j["name"] == "nightly")
    assert nightly["recipe"] == "recipes/backup.yaml"
    assert nightly["context"] == {"db": "main"}


def test_unschedule_removes_job(tmp_path):
    """Unscheduling removes the job."""
    sched = CronScheduler({"log_path": str(tmp_path / "cron.jsonl")})
    sched.schedule("temp", "@hourly", "recipes/temp.yaml")
    assert len(sched.list_jobs()) == 1

    assert sched.unschedule("temp")
    assert len(sched.list_jobs()) == 0
    assert not sched.unschedule("temp")  # already gone


def test_job_due_detection():
    """is_due correctly matches schedule to time."""
    # Schedule: minute=30, hour=14
    schedule = parse_cron_expression("30 14 * * *")

    matching = datetime(2025, 6, 15, 14, 30, 0, tzinfo=timezone.utc)
    assert is_due(schedule, matching)

    wrong_minute = datetime(2025, 6, 15, 14, 0, 0, tzinfo=timezone.utc)
    assert not is_due(schedule, wrong_minute)

    wrong_hour = datetime(2025, 6, 15, 10, 30, 0, tzinfo=timezone.utc)
    assert not is_due(schedule, wrong_hour)

    # @hourly — minute=0, hour=None
    hourly = parse_cron_expression("@hourly")
    assert is_due(hourly, datetime(2025, 6, 15, 9, 0, tzinfo=timezone.utc))
    assert not is_due(hourly, datetime(2025, 6, 15, 9, 15, tzinfo=timezone.utc))


def test_automation_profile_attached(tmp_path):
    """Automation profile is stored and accessible."""
    profile = {"allowed_tools": ["read_file", "grep", "bash"]}
    sched = CronScheduler({
        "log_path": str(tmp_path / "cron.jsonl"),
        "automation_profile": profile,
    })
    assert sched.get_automation_profile() == profile
    assert sched.get_automation_profile()["allowed_tools"] == [
        "read_file", "grep", "bash"
    ]
