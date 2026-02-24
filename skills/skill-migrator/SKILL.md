---
name: skill-migrator
version: 1.0.0
description: Translate OpenClaw TypeScript skills to Amplifier-native SKILL.md format using LLM-powered gene transfer
tags:
  - migration
  - openclaw
  - skills
  - translation
---

# Skill Migrator — OpenClaw → Amplifier Translation

## Overview

This skill teaches you to port OpenClaw (OC) TypeScript skills to Amplifier-native SKILL.md format. The process is LLM-powered gene transfer — you extract the *intent and workflows* from OC source, then rewrite them using Amplifier's tool ecosystem. You are NOT transpiling TypeScript to Python. You are translating capability intent from one platform to another.

## The 4-Step Process

### Step 1: Parse OpenClaw Source

Read the OC skill's three source files:

| OC File | What It Contains | What You Extract |
|---------|------------------|------------------|
| `SKILL.md` | User-facing instructions, workflows, examples | Core intent, step sequences, domain knowledge |
| `index.ts` | Tool schemas, API calls, TypeScript logic | Which APIs are called, parameters, response handling |
| `config.json` | Configurable parameters, API keys, defaults | What secrets/env vars are needed |

**Do NOT** try to understand the full TypeScript implementation. Focus on *what the skill does*, not *how the OC runtime executes it*.

### Step 2: Gene Transfer (the core translation)

Map OC concepts to Amplifier equivalents:

| OpenClaw Concept | Amplifier Equivalent | Notes |
|------------------|----------------------|-------|
| `index.ts` tool definitions | `bash`, `web_fetch`, `sandbox` tool calls | Amplifier agents call tools directly; no custom tool schemas |
| `config.json` parameters | Secrets via `tool-secrets` (`set_secret`/`get_secret`) | API keys → secrets (category: `api_key`); other config → env vars or inline |
| OC `SKILL.md` instructions | Amplifier `SKILL.md` body | Preserve workflows, adapt platform references |
| OC `runTool()` / `callAPI()` | `web_fetch` for HTTP APIs, `bash` for CLI tools | Direct tool invocation, no middleware |
| OC skill config UI | Onboarding recipe step or inline prompting | Skills don't have config UIs; use recipes or ask-on-first-use |
| OC `context.user` / `context.config` | `secrets get_secret` / `memory search_memories` | User context comes from Amplifier's memory and secrets systems |
| OC scheduled triggers | Cron jobs via gateway `CronScheduler` | Map OC intervals to cron expressions |

**Key translation rules:**

1. **API calls**: OC `callAPI(url, params)` → Amplifier `web_fetch(url)` with proper headers. Store API keys via `secrets set_secret name="service/api_key" value="..." category="api_key"`.

2. **File operations**: OC file handling → Amplifier `bash` with standard CLI tools (`curl`, `jq`, `python3`). For complex file generation (DOCX, PDF), use the existing document skills as patterns.

3. **External CLIs**: OC skills that shell out → Amplifier `bash` directly. Check if the CLI is installed first.

4. **Stateful workflows**: OC skills with multi-step state → Use `memory store_memory` for persistence across sessions, or instruct the agent to track state in conversation.

5. **Platform-specific features**: Discard OC-specific features (OC runtime hooks, OC plugin system, OC UI components). Replace with Amplifier equivalents or note as "not applicable."

### Step 3: Generate Amplifier SKILL.md

Write the new SKILL.md with:

```yaml
---
name: skill-name
version: 1.0.0
description: One-liner (max 100 chars)
tags:
  - relevant
  - tags
---
```

**Body structure:**
1. **Overview** — What this skill does (1-2 sentences)
2. **Prerequisites** — Required tools, API keys, installed CLIs
3. **Setup** — First-time configuration steps (storing API keys via secrets)
4. **Workflows** — Step-by-step procedures the agent follows
5. **Examples** — Concrete input/output examples
6. **Troubleshooting** — Common issues and fixes

**Companion files** (create if needed):
- `scripts/` — Helper scripts for complex operations (Python, bash)
- `references/` — API documentation, schema references
- `requirements.txt` — Python package dependencies

### Step 4: Validate

Run this checklist on every migrated skill:

- [ ] **Frontmatter valid** — `name`, `version`, `description`, `tags` all present
- [ ] **No OC references** — Search for `openclaw`, `OC`, `runTool`, `callAPI`, `config.json`, `index.ts` — none should remain
- [ ] **Tools exist** — Every tool referenced in workflows exists in Amplifier (`bash`, `web_fetch`, `secrets`, `memory`, `sandbox`, etc.)
- [ ] **Secrets documented** — Any required API keys list the `set_secret` command in Setup
- [ ] **load_skill works** — `load_skill(skill_name="skill-name")` loads without error
- [ ] **No TypeScript** — No `.ts` files in the skill directory
- [ ] **Self-contained** — Skill works without importing OC modules or depending on OC runtime

## Example Translation

**Before (OpenClaw GitHub skill — `index.ts` excerpt):**
```typescript
const tools = [{
  name: "github_search",
  description: "Search GitHub repositories",
  parameters: { query: { type: "string" }, sort: { type: "string" } }
}];
async function github_search(params) {
  const token = context.config.github_token;
  return callAPI(`https://api.github.com/search/repositories?q=${params.query}`, {
    headers: { Authorization: `token ${token}` }
  });
}
```

**After (Amplifier SKILL.md excerpt):**
```markdown
## Setup

Store your GitHub personal access token:
Use the secrets tool: `set_secret name="github/api_key" value="ghp_..." category="api_key"`

## Workflows

### Search Repositories
1. Retrieve token: `get_secret name="github/api_key"`
2. Search: `web_fetch url="https://api.github.com/search/repositories?q={query}&sort={sort}" headers={"Authorization": "token {api_key}"}`
3. Parse JSON response and present results
```

## Priority List for Migration

When the OpenClaw source repo is available, migrate in this order:

| Priority | Skills | Rationale |
|----------|--------|-----------|
| **High** | GitHub, Notion, 1Password, Obsidian, Apple Reminders | Most-used API integrations |
| **Medium** | Spotify, Weather, Apple Notes, Google Calendar | Popular but less critical |
| **Lower** | Coding agent, Discord-specific, Slack-specific | Partially covered by existing Amplifier capabilities |
