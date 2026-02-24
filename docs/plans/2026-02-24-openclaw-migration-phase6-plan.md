# OpenClaw Migration Phase 6: Skill Migration — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Commit 15 already-authored Amplifier-native skills plus their routing infrastructure (specialist agents, behavior bundle, context routing table), and build the skill migration tool and recipe for future OpenClaw skill porting.

**Architecture:** Content-only phase — no new Python code, no modules, no middleware. Part A commits 15 untracked skills covering document, creative, developer, and communication domains. Part B commits 2 specialist agents plus a behavior bundle and context routing table that orchestrate those skills. Part C creates a skill-migrator meta-skill and a staged migration recipe for future batch porting of ~32 OpenClaw TypeScript skills.

**Tech Stack:** Markdown (SKILL.md, agent descriptions, context files), YAML (behavior bundle, recipe). No Python.

**Design Document:** `docs/plans/2026-02-24-openclaw-migration-phase6-skills-design.md`

---

## ⚠️ CRITICAL: Work in Main Directory — NOT a Worktree

**This phase is an exception to the normal worktree workflow.** The 15 skills, 2 agents, behavior file, and context file exist as **untracked files in the main working directory** at `~/dev/amplifier-bundle-letsgo`. Git worktrees only contain tracked files — a new worktree would NOT have these untracked files.

**Execute all tasks directly in `~/dev/amplifier-bundle-letsgo` on a feature branch created from main.**

Setup:
```bash
cd ~/dev/amplifier-bundle-letsgo
git checkout -b feat/openclaw-migration-phase6-skills
```

Do NOT use `git worktree add`. Do NOT create a `.worktrees/` directory for this phase.

---

## Conventions Reference

**Skill directory structure (from existing committed skills):**
```
skills/{skill-name}/
├── SKILL.md                   # YAML frontmatter + markdown body (required)
├── LICENSE.txt                # License file (most skills have this)
├── requirements.txt           # Python deps if needed (some skills)
├── scripts/                   # Companion scripts (some skills)
├── references/                # Reference docs (some skills)
├── templates/                 # Template files (some skills)
└── examples/                  # Example files (some skills)
```

**SKILL.md frontmatter pattern:**
```yaml
---
name: skill-name
version: 1.0.0
description: One-liner describing what the skill does
tags:
  - tag1
  - tag2
---

# Skill Name

Markdown body with instructions, workflows, examples.
```

**Agent description pattern (from `agents/gateway-operator.md`):**
- Markdown file with agent role, capabilities, and routing instructions.

**Behavior YAML pattern (from `behaviors/gateway.yaml`):**
```yaml
bundle:
  name: behavior-name
  version: 1.0.0
  description: One-liner

context:
  include:
    - path/to/context.md
```

**Recipe YAML pattern (from `recipes/setup-wizard.yaml`):**
```yaml
schema: v1.7.0

name: recipe-name
description: One-liner
version: 1.0.0
author: letsgo
tags: [tag1, tag2]

context:
  variable_name: ""

stages:
  - name: stage-name
    description: What this stage does
    steps:
      - id: step-id
        agent: self
        prompt: >
          Instructions for the agent.
        output: variable_name
        timeout: 300
    approval: true
```

---

## Inventory of Untracked Files

### 15 Skills (with their companion files)

| Skill | Category | Contents |
|-------|----------|----------|
| `algorithmic-art` | Creative | SKILL.md, LICENSE.txt, templates/ |
| `brand-guidelines` | Creative | SKILL.md, LICENSE.txt |
| `canvas-design` | Creative | SKILL.md, LICENSE.txt, requirements.txt, canvas-fonts/ (~30 font files) |
| `doc-coauthoring` | Communication | SKILL.md |
| `docx` | Document | SKILL.md, LICENSE.txt, requirements.txt, scripts/ |
| `frontend-design` | Creative | SKILL.md, LICENSE.txt |
| `internal-comms` | Communication | SKILL.md, LICENSE.txt, examples/ |
| `mcp-builder` | Developer | SKILL.md, LICENSE.txt, reference/, scripts/ |
| `pdf` | Document | SKILL.md, LICENSE.txt, requirements.txt, scripts/, forms.md, reference.md |
| `pptx` | Document | SKILL.md, LICENSE.txt, requirements.txt, scripts/, editing.md, pptxgenjs.md |
| `slack-gif-creator` | Creative | SKILL.md, LICENSE.txt, requirements.txt, core/ |
| `theme-factory` | Creative | SKILL.md, LICENSE.txt, themes/, theme-showcase.pdf |
| `web-artifacts-builder` | Developer | SKILL.md, LICENSE.txt, scripts/ |
| `webapp-testing` | Developer | SKILL.md, LICENSE.txt, requirements.txt, scripts/, examples/ |
| `xlsx` | Document | SKILL.md, LICENSE.txt, requirements.txt, scripts/ |

### Skill Creator Companion Files (already committed: `skills/skill-creator/SKILL.md`)

| Path | Contents |
|------|----------|
| `skills/skill-creator/references/` | output-patterns.md, workflows.md |
| `skills/skill-creator/scripts/` | init_skill.py, quick_validate.py, package_skill.py |

### Routing Infrastructure

| File | Type |
|------|------|
| `agents/creative-specialist.md` | Agent — orchestrates 6 creative skills |
| `agents/document-specialist.md` | Agent — orchestrates 4 document skills |
| `behaviors/skills.yaml` | Behavior bundle — skill discovery + specialist routing |
| `context/skills-awareness.md` | Context — master routing table for 20 skills |

---

## Task 1: Commit 15 Untracked Skills + Skill Creator Companions

**Files:** All 15 skill directories listed above + `skills/skill-creator/references/` + `skills/skill-creator/scripts/`

### Step 1: Verify all skill directories exist and have SKILL.md

Run:
```bash
cd ~/dev/amplifier-bundle-letsgo
for d in algorithmic-art brand-guidelines canvas-design doc-coauthoring docx frontend-design internal-comms mcp-builder pdf pptx slack-gif-creator theme-factory web-artifacts-builder webapp-testing xlsx; do
  if [ -f "skills/$d/SKILL.md" ]; then echo "OK: $d"; else echo "MISSING: $d"; fi
done
echo "---"
ls skills/skill-creator/references/ skills/skill-creator/scripts/
```

Expected: All 15 show `OK`, references and scripts directories list their files.

### Step 2: Stage all skill files

```bash
git add \
  skills/algorithmic-art/ \
  skills/brand-guidelines/ \
  skills/canvas-design/ \
  skills/doc-coauthoring/ \
  skills/docx/ \
  skills/frontend-design/ \
  skills/internal-comms/ \
  skills/mcp-builder/ \
  skills/pdf/ \
  skills/pptx/ \
  skills/slack-gif-creator/ \
  skills/theme-factory/ \
  skills/web-artifacts-builder/ \
  skills/webapp-testing/ \
  skills/xlsx/ \
  skills/skill-creator/references/ \
  skills/skill-creator/scripts/
```

### Step 3: Commit

```bash
git commit -m "feat(skills): commit 15 Amplifier-native skills — document, creative, developer, communication

Document: docx, pdf, pptx, xlsx
Creative: algorithmic-art, brand-guidelines, canvas-design, frontend-design, slack-gif-creator, theme-factory
Developer: mcp-builder, web-artifacts-builder, webapp-testing
Communication: doc-coauthoring, internal-comms

Also includes skill-creator companion files (references + scripts)."
```

### Step 4: Verify commit

```bash
git log --oneline -1
git diff --stat HEAD~1
```

Expected: One commit with ~40+ files added.

---

## Task 2: Commit Specialist Agents + Routing Infrastructure

**Files:**
- `agents/creative-specialist.md`
- `agents/document-specialist.md`
- `behaviors/skills.yaml`
- `context/skills-awareness.md`

### Step 1: Verify all files exist

```bash
ls -la agents/creative-specialist.md agents/document-specialist.md behaviors/skills.yaml context/skills-awareness.md
```

### Step 2: Stage

```bash
git add agents/creative-specialist.md agents/document-specialist.md behaviors/skills.yaml context/skills-awareness.md
```

### Step 3: Commit

```bash
git commit -m "feat(skills): add specialist agents, skill routing behavior, and awareness context

- agents/creative-specialist.md — orchestrates 6 creative skills
- agents/document-specialist.md — orchestrates 4 document skills
- behaviors/skills.yaml — skill discovery and specialist agent routing
- context/skills-awareness.md — master routing table mapping 20 intents to skills/agents"
```

### Step 4: Verify commit

```bash
git log --oneline -1
git diff --stat HEAD~1
```

Expected: 4 files added.

---

## Task 3: Create Skill Migrator Meta-Skill

**Files:**
- Create: `skills/skill-migrator/SKILL.md`

### Step 1: Create directory

```bash
mkdir -p skills/skill-migrator
```

### Step 2: Write SKILL.md

Create `skills/skill-migrator/SKILL.md` with the following content:

```markdown
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
```

### Step 3: Commit

```bash
git add skills/skill-migrator/
git commit -m "feat(skills): add skill-migrator meta-skill for OpenClaw → Amplifier translation"
```

### Step 4: Verify

```bash
git log --oneline -1
ls skills/skill-migrator/SKILL.md
```

---

## Task 4: Create Skill Migration Recipe

**Files:**
- Create: `recipes/skill-migration.yaml`

### Step 1: Write the recipe

Create `recipes/skill-migration.yaml` with the following content:

```yaml
schema: v1.7.0

name: skill-migration
description: Batch-migrate OpenClaw TypeScript skills to Amplifier-native format with review gates
version: 1.0.0
author: letsgo
tags:
  - skills
  - migration
  - openclaw
  - batch

context:
  source_dir: ""
  priority: "all"

stages:
  - name: discover
    description: Scan OpenClaw skills directory and categorize by migration priority
    steps:
      - id: scan-skills
        agent: self
        prompt: >
          Scan the OpenClaw skills directory at {{source_dir}} for skills to migrate.

          For each skill found, read its source files (SKILL.md, index.ts, config.json)
          and categorize it:

          **Priority levels:**
          - **high**: GitHub, Notion, 1Password, Obsidian, Apple Reminders
          - **medium**: Spotify, Weather, Apple Notes, Google Calendar
          - **low**: Everything else

          **Filter:** Only include skills matching priority "{{priority}}"
          (use "all" to include everything).

          For each skill, report:
          1. Skill name
          2. Priority level
          3. What it does (one sentence from OC SKILL.md)
          4. API dependencies (from index.ts)
          5. Config parameters needed (from config.json)
          6. Estimated complexity: simple (direct API mapping), moderate (multi-step
             workflows), complex (stateful, multi-API, or heavy logic)

          Present a summary table and recommend a migration order
          (simple skills first to build momentum).

          If {{source_dir}} is empty or does not exist, report the error and stop.
        output: skill_inventory
        timeout: 600
    approval: true

  - name: migrate
    description: Translate each selected skill using the 4-step gene transfer process
    steps:
      - id: load-migrator
        agent: self
        prompt: >
          Load the skill-migrator skill for reference:
          Use load_skill(skill_name="skill-migrator") to get the full translation guide.

          Then for each skill in the approved inventory from {{skill_inventory}},
          execute the 4-step migration process:

          1. **Parse**: Read the OC source files (SKILL.md, index.ts, config.json)
          2. **Gene transfer**: Map OC patterns to Amplifier equivalents using the
             translation rules from the skill-migrator guide
          3. **Generate**: Write the new SKILL.md with proper frontmatter and body.
             Create companion files (scripts/, references/) if the skill needs them.
             Save to skills/{skill-name}/SKILL.md
          4. **Validate**: Run the quality checklist — no OC references, valid frontmatter,
             all referenced tools exist, secrets documented

          For each migrated skill, report:
          - Status: success / needs-review / failed
          - Files created
          - Any areas flagged for manual review
          - Validation checklist results

          Work through skills one at a time. If a skill is too complex to migrate
          automatically, flag it as "needs-review" with specific notes on what
          requires human judgment.
        output: migration_results
        timeout: 1800

  - name: review
    description: Validate migrated skills and flag issues for human review
    steps:
      - id: validate-batch
        agent: self
        prompt: >
          Review all migrated skills from {{migration_results}}.

          For each skill:
          1. Read the generated SKILL.md
          2. Verify frontmatter is valid YAML with name, version, description, tags
          3. Search for any remaining OpenClaw references (openclaw, OC, runTool,
             callAPI, config.json, index.ts) — flag if found
          4. Verify all tool references exist in Amplifier (bash, web_fetch, secrets,
             memory, sandbox, read_file, write_file, grep, glob, web_search)
          5. Check that API key setup instructions use the secrets tool with the
             naming convention: {service}/api_key
          6. Verify the skill loads: load_skill(skill_name="{name}") should not error

          Present a review summary:
          - **Approved**: Passed all checks, ready to commit
          - **Needs fixes**: List specific issues to address
          - **Rejected**: Too many issues, needs manual rewrite

          For "needs fixes" skills, attempt the fixes and re-validate.
        output: review_results
        timeout: 900
    approval: true

  - name: commit
    description: Stage and commit approved migrated skills
    steps:
      - id: commit-approved
        agent: self
        prompt: >
          Based on the review results from {{review_results}}, commit only the
          **approved** skills.

          For each approved skill:
          1. Stage: git add skills/{skill-name}/
          2. Verify staged files look correct: git diff --cached --name-only

          Commit all approved skills in a single commit:
          git commit -m "feat(skills): migrate {N} OpenClaw skills to Amplifier-native format

          Migrated: {comma-separated list of skill names}
          Source: {source_dir}"

          Report:
          - Number of skills committed
          - Number of skills deferred (needs-review or rejected)
          - The commit hash

          If any skills were deferred, list them with the reason so they can be
          addressed in a follow-up.
        output: commit_results
        timeout: 300
```

### Step 2: Validate YAML

Run:
```bash
python3 -c "import yaml; yaml.safe_load(open('recipes/skill-migration.yaml')); print('Valid YAML')"
```

Expected: `Valid YAML`

### Step 3: Commit

```bash
git add recipes/skill-migration.yaml
git commit -m "feat(skills): add skill-migration recipe for batch OpenClaw skill porting"
```

### Step 4: Verify

```bash
git log --oneline -1
```

---

## Task 5: Final Verification

### Step 1: Verify working tree is clean

```bash
git status
```

Expected: No untracked skill/agent/behavior/context files remain. Working tree should be clean (or only have files unrelated to Phase 6).

### Step 2: Show commit sequence

```bash
git log --oneline -5
```

Expected: 4 commits on `feat/openclaw-migration-phase6-skills`:
```
xxxxxxx feat(skills): add skill-migration recipe for batch OpenClaw skill porting
xxxxxxx feat(skills): add skill-migrator meta-skill for OpenClaw → Amplifier translation
xxxxxxx feat(skills): add specialist agents, skill routing behavior, and awareness context
xxxxxxx feat(skills): commit 15 Amplifier-native skills — document, creative, developer, communication
```

### Step 3: Verify file counts

```bash
echo "Total skills:" && ls -d skills/*/  | wc -l
echo "Total agents:" && ls agents/*.md | wc -l
echo "Total behaviors:" && ls behaviors/*.yaml | wc -l
echo "Skill migrator:" && ls skills/skill-migrator/SKILL.md
echo "Migration recipe:" && ls recipes/skill-migration.yaml
```

Expected:
- Total skills: 21 (5 previously committed + 15 new + 1 skill-migrator)
- Total agents: 5 (3 previously committed + 2 new)
- Behaviors: count includes the new `skills.yaml`
- Both new files exist

---

## Summary

| Task | What Ships | Commit Message | Files |
|------|-----------|----------------|-------|
| 1 | 15 Amplifier-native skills + skill-creator companions | `feat(skills): commit 15 Amplifier-native skills — document, creative, developer, communication` | ~100+ files |
| 2 | 2 specialist agents + behavior + context routing | `feat(skills): add specialist agents, skill routing behavior, and awareness context` | 4 files |
| 3 | Skill migrator meta-skill | `feat(skills): add skill-migrator meta-skill for OpenClaw → Amplifier translation` | 1 file |
| 4 | Skill migration recipe | `feat(skills): add skill-migration recipe for batch OpenClaw skill porting` | 1 file |
| 5 | Final verification | (no commit) | 0 files |

**Total new tests:** 0 (no Python code in this phase)
**Total new files:** ~107 (existing untracked) + 2 (newly created)
**Estimated execution time:** Single batch — fastest phase yet
