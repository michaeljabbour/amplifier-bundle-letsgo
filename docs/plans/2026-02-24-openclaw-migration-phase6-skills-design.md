# OpenClaw Migration Phase 6: Skill Migration — Design

## Goal

Commit the 15 already-authored Amplifier-native skills plus their routing infrastructure (specialist agents, behavior bundle, context routing table), build the skill migration tool and recipe for future OpenClaw skill porting, and defer the actual ~32 OC API-integration skill migrations until the OpenClaw source repo is accessible.

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Scope | Commit existing + build migration tool | Ships real value (20 skills + routing) while setting up the pipeline |
| OC batch migration | Deferred | OpenClaw source repo not present in this repo; tool is ready when source is available |
| Migration tool | Skill + recipe (not a Python module) | LLM-powered translation is a skill pattern, not a code module |
| Existing skills | Commit as-is | Already authored in Amplifier-native format; no translation needed |

## Part A: Commit Existing Work

### 15 Untracked Skills (by category)

| Category | Skills |
|----------|--------|
| Document | `docx`, `pdf`, `pptx`, `xlsx` |
| Creative | `algorithmic-art`, `brand-guidelines`, `canvas-design`, `frontend-design`, `slack-gif-creator`, `theme-factory` |
| Developer | `mcp-builder`, `web-artifacts-builder`, `webapp-testing` |
| Communication | `doc-coauthoring`, `internal-comms` |

### Routing Infrastructure

| File | Type | Purpose |
|------|------|---------|
| `agents/creative-specialist.md` | Agent | Orchestrates 6 creative skills |
| `agents/document-specialist.md` | Agent | Orchestrates 4 document skills |
| `behaviors/skills.yaml` | Behavior | Skill discovery + specialist agent routing |
| `context/skills-awareness.md` | Context | Master routing table: 20 intents → skills/agents |

### Skill Creator Companion Files

| Path | Purpose |
|------|---------|
| `skills/skill-creator/references/` | Output patterns, workflow patterns |
| `skills/skill-creator/scripts/` | init_skill.py, quick_validate.py, package_skill.py |

## Part B: Skill Migration Tool

### `skills/skill-migrator/SKILL.md`

A meta-skill that teaches agents the 4-step OpenClaw → Amplifier translation process:

1. **Parse OC source** — Read OpenClaw SKILL.md (instructions), index.ts (tool schemas, APIs), config.json (parameters)
2. **Gene transfer (LLM-powered)** — Map OC tool definitions → Amplifier tool invocations, config → secrets + env vars, preserve core instructions/workflows, adapt platform references, discard OC internals
3. **Generate skeleton** — Write SKILL.md with proper frontmatter, companion scripts for API integrations, flag areas needing manual review
4. **Validate** — Check Amplifier skills spec compliance, verify no OC references remain, test `load_skill()` works

The skill includes:
- Translation rules for common OC patterns (tool definitions, config params, API calls)
- Mapping table: OC concepts → Amplifier equivalents
- Quality checklist for migrated skills
- Examples of before/after translations

### `recipes/skill-migration.yaml`

A staged recipe for batch migration with review gates:

```
Stage 1: Discover — Scan OC skills directory, list available skills, categorize by priority
  → Approval gate: confirm which skills to migrate

Stage 2: Migrate — For each selected skill, run the 4-step translation process
  → Output: generated SKILL.md skeletons

Stage 3: Review — Validate each migrated skill against spec, flag issues
  → Approval gate: review and approve each skill

Stage 4: Commit — Stage and commit approved skills
```

## Part C: Deferred

The actual ~32 OpenClaw API-integration skill migrations:

| Priority | Skills | Status |
|----------|--------|--------|
| High | GitHub, Notion, 1Password, Obsidian, Apple Reminders | Deferred — need OC source |
| Medium | Spotify, Weather, Apple Notes, Google Calendar | Deferred — need OC source |
| Lower | Coding agent, Discord-specific, Slack-specific | Deferred — need OC source |

The migration tool and recipe are ready. When the OpenClaw source repo is accessible, run:
```
recipes execute letsgo:recipes/skill-migration.yaml context='{"source_dir": "/path/to/openclaw/skills"}'
```

## What Phase 6 Ships

| Component | Type | What It Does |
|-----------|------|-------------|
| 15 skills | Content (SKILL.md + companions) | Document, creative, developer, communication skills |
| 2 specialist agents | Agent definitions | Creative specialist, document specialist |
| Skills behavior | Behavior YAML | Skill discovery + agent routing |
| Skills awareness | Context file | Master routing table for 20 skills |
| Skill creator extras | Scripts + references | init, validate, package scripts + pattern docs |
| Skill migrator | Meta-skill (SKILL.md) | Teaches the OC → Amplifier translation process |
| Migration recipe | Staged recipe (YAML) | Batch migration with review gates |

## What's NOT in Phase 6

| Deferred | Rationale | When |
|----------|-----------|------|
| ~32 OC API-integration skills | OpenClaw source not available | Phase 6.1 when OC source is accessible |
| Automated TypeScript parser | LLM-powered gene transfer is the approach; no need for a TS parser | Not planned |
| Skill registry/marketplace | Future ecosystem concern; Amplifier's skill system handles discovery | Not planned |

## Estimated Scope

| Metric | Value |
|--------|-------|
| Files committed (existing) | ~40+ (15 skills × ~2-3 files each + agents + behavior + context) |
| Files created (new) | ~3 (skill-migrator SKILL.md + recipe YAML + any companions) |
| New code | ~0 (all content/YAML files) |
| Tests | ~0 (no new Python code) |
| Tasks | 5 |

---

*Phase 6 ships the skill ecosystem infrastructure. The migration pipeline is ready for when the OpenClaw source becomes available.*