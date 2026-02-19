---
name: schedule
version: 1.0.0
description: >-
    Scheduled task management for the letsgo gateway. Use when the user wants to
    schedule a recurring task, set up a cron job that triggers an Amplifier
    recipe, list existing scheduled jobs, delete a scheduled job, or automate
    periodic work (reports, health checks, reminders, syncs). Operates through
    the gateway's CronScheduler.
---

# Schedule Skill

Manage cron-based scheduled tasks through the letsgo gateway's `CronScheduler`. Each schedule fires at a cron interval and executes an Amplifier recipe, enabling periodic automated work without manual invocation.

## When to Use

- Schedule a recurring task (daily reports, periodic health checks, weekly reviews)
- Set up a cron job that triggers an Amplifier recipe on a schedule
- List existing scheduled jobs managed by the gateway
- Delete or modify a scheduled job
- Automate periodic agent work (metrics, syncs, reminders)

## Architecture Overview

The letsgo gateway includes a `CronScheduler` (defined in `gateway/letsgo_gateway/cron.py`) that manages `CronJob` objects. When a job is due, the scheduler executes the associated Amplifier recipe through the gateway daemon's orchestration loop.

**Key components:**
- `CronScheduler` -- manages job registration, scheduling, and execution
- `CronJob` -- data model for a scheduled job (expression, recipe path, label, metadata)
- `parse_cron_expression` / `is_due` -- cron expression parsing and evaluation
- `GatewayDaemon` -- top-level orchestrator that runs the scheduler alongside channel adapters and the session router

## Commands (letsgo-gateway CLI)

The `letsgo-gateway` CLI provides cron management subcommands.

### Create a scheduled job

```bash
letsgo-gateway cron create \
  --expression "0 9 * * *" \
  --recipe "recipes/daily-digest.yaml" \
  --label "daily-digest" \
  [--context '{"key": "value"}']
```

**Parameters:**
- `--expression` -- Cron expression or shorthand (required). See syntax reference below.
- `--recipe` -- Path to the Amplifier recipe YAML to execute (required). Supports `@bundle:path` notation.
- `--label` -- Unique label to identify this job (required). Use descriptive names for easy management.
- `--context` -- Optional JSON string of context variables passed to the recipe at execution time.

### List scheduled jobs

```bash
letsgo-gateway cron list
```

Displays all registered cron jobs with their expression, recipe, label, and next scheduled run.

### Delete a scheduled job

```bash
letsgo-gateway cron delete --label "daily-digest"
```

Remove a specific job by label.

## Cron Expression Syntax

### Shorthand expressions

| Shorthand | Equivalent | Meaning |
|-----------|-----------|---------|
| `@hourly` | `0 * * * *` | Every hour at minute 0 |
| `@daily` | `0 0 * * *` | Every day at midnight |
| `@weekly` | `0 0 * * 0` | Every Sunday at midnight |

### Standard 5-field expressions

```
+------------- minute (0-59)
| +----------- hour (0-23)
| | +--------- day of month (1-31)
| | | +------- month (1-12)
| | | | +----- day of week (0-7, 0 and 7 = Sunday)
| | | | |
* * * * *
```

| Pattern | Meaning |
|---------|---------|
| `0 9 * * *` | Daily at 9:00 AM |
| `0 9 * * 1-5` | Weekdays at 9:00 AM |
| `*/15 * * * *` | Every 15 minutes |
| `0 */2 * * *` | Every 2 hours |
| `0 0 * * 0` | Weekly on Sunday midnight |
| `0 0 1 * *` | Monthly on the 1st |
| `30 8 * * 1` | Monday at 8:30 AM |
| `MM HH * * *` | Daily at HH:MM (replace MM and HH) |

## Workflow

1. Identify or create the Amplifier recipe to run on schedule.
2. Determine the cron expression from the user's description (e.g., "every morning" -> `0 9 * * *`).
3. Choose a descriptive label for the job.
4. Optionally prepare context variables the recipe needs at runtime.
5. Run `letsgo-gateway cron create` with the parameters.
6. Verify with `letsgo-gateway cron list`.

## Examples

### Daily digest recipe

```bash
letsgo-gateway cron create \
  --expression "0 9 * * *" \
  --recipe "recipes/daily-digest.yaml" \
  --label "morning-digest"
```

### Periodic health check

```bash
letsgo-gateway cron create \
  --expression "*/30 * * * *" \
  --recipe "recipes/health-check.yaml" \
  --label "health-check-30m"
```

### Weekly code review reminder

```bash
letsgo-gateway cron create \
  --expression "0 10 * * 1" \
  --recipe "recipes/pr-review.yaml" \
  --label "weekly-pr-review"
```

### Scheduled job with context

```bash
letsgo-gateway cron create \
  --expression "@daily" \
  --recipe "recipes/report.yaml" \
  --label "daily-report" \
  --context '{"report_type": "metrics", "recipients": ["team"]}'
```

### List and clean up

```bash
# See all scheduled jobs
letsgo-gateway cron list

# Remove one
letsgo-gateway cron delete --label "health-check-30m"
```

## How It Works

1. The `GatewayDaemon` starts the `CronScheduler` as part of its event loop.
2. The scheduler evaluates each registered `CronJob` against the current time using `is_due()`.
3. When a job is due, the scheduler invokes the associated Amplifier recipe via the recipes execution engine, passing any stored context variables.
4. Recipe execution follows standard Amplifier patterns -- sequential steps, agent delegation, approval gates (for staged recipes), and state persistence.
5. Results flow back through the gateway's normal response path (channel adapters, session router).

**Key difference from raw crontab:** Jobs are managed as `CronJob` data objects within the gateway process, not as system crontab entries. This means jobs survive gateway restarts (persisted to config), have structured metadata, and integrate directly with Amplifier's recipe and session infrastructure.

## Gateway Module Reference

- `gateway/letsgo_gateway/cron.py` -- `CronScheduler`, `CronJob`, `parse_cron_expression`, `is_due`
- `gateway/letsgo_gateway/daemon.py` -- `GatewayDaemon` (orchestrates scheduler + adapters + router)
- `gateway/letsgo_gateway/cli.py` -- CLI entry point (`letsgo-gateway` command)

## Tips

- Use `@daily`, `@hourly`, `@weekly` shorthands for common intervals -- they're clearer than raw expressions
- Always verify with `letsgo-gateway cron list` after creating a job
- Use descriptive labels -- they're the primary way to identify and manage jobs
- Pass runtime context via `--context` rather than hardcoding values in recipes
- Pair scheduled jobs with recipes that have built-in error handling for unattended execution
- For time-sensitive jobs, note that the scheduler checks on a polling interval -- exact-second precision is not guaranteed
