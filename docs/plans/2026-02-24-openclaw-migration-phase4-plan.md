# OpenClaw Migration Phase 4: `letsgo-browser` Satellite Bundle — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add browser automation to the LetsGo ecosystem by composing the existing `amplifier-bundle-browser-tester` bundle with gateway-specific context, skills, and onboarding recipe updates.

**Architecture:** Pure composition — no new Python modules, no gateway middleware, no tool code. The satellite includes the external `browser-tester` bundle (3 agents + `agent-browser` CLI) and layers gateway-specific context and two existing skills (`agent-browser`, `webapp-testing`) on top. This is the leanest phase in the migration.

**Tech Stack:** YAML bundle manifests, markdown context/skill files, recipe YAML. No Python code.

**Design Document:** `docs/plans/2026-02-24-openclaw-migration-phase4-browser-design.md`

---

## Conventions Reference

These conventions are derived from the existing codebase. Follow them exactly.

**Satellite bundle structure (from voice, canvas):**
```
{satellite}/
├── bundle.md                          # YAML frontmatter + markdown body with @context include
├── behaviors/
│   └── {name}-capabilities.yaml       # bundle: header + optional tools: + context.include:
├── context/
│   └── {name}-awareness.md            # Agent-facing instructions
└── skills/
    └── {skill-name}/
        └── SKILL.md                   # YAML frontmatter + markdown body
```

**Bundle.md pattern (from `voice/bundle.md`):**
```yaml
---
bundle:
  name: letsgo-{name}
  version: 0.1.0
  description: One-liner
includes:
  - bundle: letsgo-{name}:behaviors/{name}-capabilities
---

# LetsGo {Name}

Description paragraph.

@letsgo-{name}:context/{name}-awareness.md
```

**Behavior YAML pattern (from `canvas/behaviors/canvas-capabilities.yaml`):**
```yaml
bundle:
  name: behavior-{name}-capabilities
  version: 1.0.0
  description: One-liner

context:
  include:
    - letsgo-{name}:context/{name}-awareness.md
```

Note: Behaviors with no tool modules omit the `tools:` section entirely.

**Setup wizard recipe pattern (from `recipes/setup-wizard.yaml`):**
- Satellite config steps go in the `satellite-setup` stage, after `select-satellites`
- Each step checks `{{satellite_config}}` to skip if not selected
- Output variable follows `{name}_config` pattern
- Approval prompt lists all satellite config variables

**Capability contracts pattern (from `docs/CAPABILITY_CONTRACTS.md`):**
- Each capability documents: registered by, required by, interface, graceful degradation

---

## Summary

| Task | What Ships | Files | Commit Message |
|------|-----------|-------|----------------|
| 1 | Satellite bundle structure | 3 new | `feat(browser): satellite bundle structure — bundle.md, behavior, context` |
| 2 | Browser skills (existing, moved) | ~17 copied | `feat(browser): commit agent-browser and webapp-testing skills` |
| 3 | Setup wizard recipe update | 1 modified | `feat(browser): add browser configuration step to setup-wizard recipe` |
| 4 | Capability contracts update | 1 modified | `docs: add browser composition-only pattern to capability contracts` |
| 5 | Final verification | 0 | (no commit — verification only) |

---

## Task 1: Satellite Bundle Structure

**Files:**
- Create: `browser/bundle.md`
- Create: `browser/behaviors/browser-capabilities.yaml`
- Create: `browser/context/browser-awareness.md`

### Step 1: Create the bundle manifest

Create `browser/bundle.md`:

```yaml
---
bundle:
  name: letsgo-browser
  version: 0.1.0
  description: Browser automation for LetsGo — general browsing, research, visual documentation, and gateway-specific workflows
includes:
  - amplifier-bundle-browser-tester
  - bundle: letsgo-browser:behaviors/browser-capabilities
---

# LetsGo Browser

Browser automation capabilities for the LetsGo gateway — composes the browser-tester bundle for general web automation with gateway-specific context and skills.

@letsgo-browser:context/browser-awareness.md
```

### Step 2: Create the behavior YAML

Create `browser/behaviors/browser-capabilities.yaml`:

```yaml
bundle:
  name: behavior-browser-capabilities
  version: 1.0.0
  description: Browser automation capabilities for LetsGo gateway

context:
  include:
    - letsgo-browser:context/browser-awareness.md
```

Note: No `tools:` section — the `browser-tester` bundle provides the `agent-browser` CLI tool via its own behavior. This satellite adds only context and skills.

### Step 3: Create the context file

Create `browser/context/browser-awareness.md`:

```markdown
# Browser Capabilities

You have access to browser automation through the LetsGo gateway via the browser-tester bundle.

## Available Agents

Three specialized browser agents are available — delegate to them for browser tasks:

- **browser-operator** — General-purpose automation: navigate pages, fill forms, click buttons, extract data, take screenshots. The workhorse for any browser interaction.
- **browser-researcher** — Multi-page research: explore documentation, compare competitors, synthesize findings from multiple sites. Returns structured summaries with source citations.
- **visual-documenter** — Visual documentation: capture screenshots at multiple viewports, document UI flows step-by-step, create before/after comparisons for QA evidence.

All three agents use the `agent-browser` CLI under the hood. Delegate browser work to them rather than running `agent-browser` commands directly — the agents handle retry logic, snapshot lifecycle, and failure budgets.

## Gateway-Specific Use Cases

Browser automation integrates with the LetsGo gateway in several ways:

- **Channel onboarding assistance** — During WhatsApp setup, use browser-operator to navigate to web.whatsapp.com and capture QR code screenshots for the user. Similarly, help with OAuth-based channel setup (Discord bot portal, Slack app configuration).
- **Gateway endpoint testing** — Use browser-operator to verify webhook endpoints, test the canvas web UI at `localhost:8080/canvas`, or validate that the gateway's HTTP routes respond correctly.
- **Research for configuration** — Use browser-researcher to look up channel API documentation (Telegram Bot API, Discord Developer Portal, Signal CLI docs) when helping users configure channels.

## Integration with Canvas

If the canvas satellite (`letsgo-canvas`) is enabled, browser agents can push visual results to the canvas:

- Take a screenshot with browser-operator, then use `canvas_push` with `content_type: "html"` to display it
- Extract tabular data from a webpage and push it via `canvas_push` with `content_type: "table"`
- Capture Vega-Lite chart specs from data visualization sites and push via `canvas_push` with `content_type: "chart"`

## Skills Available

Two browser skills provide detailed reference:

- **agent-browser** — Complete CLI reference: navigation, snapshots, element refs, sessions, authentication persistence, parallel sessions, iOS simulator, JavaScript evaluation
- **webapp-testing** — Playwright-based programmatic testing: server lifecycle management, reconnaissance-then-action pattern, DOM inspection, screenshot capture
```

### Step 4: Verify YAML validity

Run:
```bash
cd <worktree> && python -c "import yaml; yaml.safe_load(open('browser/bundle.md').read().split('---')[1]); print('bundle.md OK')"
python -c "import yaml; yaml.safe_load(open('browser/behaviors/browser-capabilities.yaml')); print('behavior OK')"
```

Expected: Both print OK.

### Step 5: Commit

```bash
git add browser/
git commit -m "feat(browser): satellite bundle structure — bundle.md, behavior, context"
```

---

## Task 2: Move Browser Skills

**Files:**
- Copy: `skills/agent-browser/` → `browser/skills/agent-browser/`
- Copy: `skills/webapp-testing/` → `browser/skills/webapp-testing/`

The source skills are in the **main repo working directory** (`~/dev/amplifier-bundle-letsgo/skills/`), not the worktree. The worktree branched from `main` which has these as untracked files.

### Step 1: Copy skills to the worktree

```bash
cd <worktree>
cp -r ~/dev/amplifier-bundle-letsgo/skills/agent-browser browser/skills/agent-browser
cp -r ~/dev/amplifier-bundle-letsgo/skills/webapp-testing browser/skills/webapp-testing
```

### Step 2: Verify files copied correctly

```bash
find browser/skills -type f | sort
```

Expected output (approximately 17 files):
```
browser/skills/agent-browser/references/authentication.md
browser/skills/agent-browser/references/commands.md
browser/skills/agent-browser/references/proxy-support.md
browser/skills/agent-browser/references/session-management.md
browser/skills/agent-browser/references/snapshot-refs.md
browser/skills/agent-browser/references/video-recording.md
browser/skills/agent-browser/SKILL.md
browser/skills/agent-browser/templates/authenticated-session.sh
browser/skills/agent-browser/templates/capture-workflow.sh
browser/skills/agent-browser/templates/form-automation.sh
browser/skills/webapp-testing/examples/console_logging.py
browser/skills/webapp-testing/examples/element_discovery.py
browser/skills/webapp-testing/examples/static_html_automation.py
browser/skills/webapp-testing/LICENSE.txt
browser/skills/webapp-testing/requirements.txt
browser/skills/webapp-testing/scripts/with_server.py
browser/skills/webapp-testing/SKILL.md
```

### Step 3: Verify SKILL.md frontmatter is valid

```bash
python -c "
import yaml
for path in ['browser/skills/agent-browser/SKILL.md', 'browser/skills/webapp-testing/SKILL.md']:
    content = open(path).read()
    fm = content.split('---')[1]
    data = yaml.safe_load(fm)
    print(f'{path}: name={data[\"name\"]}, version={data[\"version\"]} OK')
"
```

Expected:
```
browser/skills/agent-browser/SKILL.md: name=agent-browser, version=1.0.0 OK
browser/skills/webapp-testing/SKILL.md: name=webapp-testing, version=1.0.0 OK
```

### Step 4: Commit

```bash
git add browser/skills/
git commit -m "feat(browser): commit agent-browser and webapp-testing skills"
```

---

## Task 3: Update Setup Wizard Recipe

**Files:**
- Modify: `recipes/setup-wizard.yaml`

### Step 1: Read the current recipe

Read `recipes/setup-wizard.yaml` and locate the `satellite-setup` stage. Find the `configure-canvas` step — the new `configure-browser` step goes immediately after it.

### Step 2: Add the configure-browser step

Insert the following step after the `configure-canvas` step and before the `approval:` block in the `satellite-setup` stage:

```yaml
      - id: configure-browser
        agent: self
        prompt: >
          If browser was selected in {{satellite_config}}:

          1. **Verify agent-browser CLI:**
             - Run: which agent-browser
             - If not found, install it:
               npm install -g agent-browser && agent-browser install
             - Verify: agent-browser --version

          2. **Report browser readiness:**
             - agent-browser CLI version
             - Chromium status (bundled with agent-browser)
             - Note: No API keys needed — browser automation is local

          If browser was NOT selected, skip this step entirely and report "Browser: skipped".
        output: browser_config
        timeout: 180
```

### Step 3: Update the approval prompt

Update the `satellite-setup` stage's `approval:` block to include `{{browser_config}}`:

```yaml
    approval:
      required: true
      prompt: |
        Satellite setup:

        {{satellite_config}}

        Voice configuration: {{voice_config}}

        Canvas configuration: {{canvas_config}}

        Browser configuration: {{browser_config}}

        Proceed to daemon startup?
```

### Step 4: Validate YAML

```bash
python -c "import yaml; yaml.safe_load(open('recipes/setup-wizard.yaml')); print('Valid YAML')"
```

Expected: `Valid YAML`

### Step 5: Commit

```bash
git add recipes/setup-wizard.yaml
git commit -m "feat(browser): add browser configuration step to setup-wizard recipe"
```

---

## Task 4: Update Capability Contracts

**Files:**
- Modify: `docs/CAPABILITY_CONTRACTS.md`

### Step 1: Read the current contracts doc

Read `docs/CAPABILITY_CONTRACTS.md`.

### Step 2: Add the browser section

Append the following section after the `secrets.redeem` section and before the `## Satellite Rules` section:

```markdown
### `browser` (composition-only)

- **Registered by:** None — `letsgo-browser` does not register any capabilities
- **Required by:** None
- **Interface:** N/A — this satellite composes `amplifier-bundle-browser-tester` (3 agents + CLI tool) and adds gateway-specific context and skills only
- **Pattern:** Composition-only satellite — no tool modules, no middleware, no capabilities. Demonstrates that a satellite can add value purely through context, skills, and bundle composition without registering any new capabilities on the coordinator.
```

### Step 3: Commit

```bash
git add docs/CAPABILITY_CONTRACTS.md
git commit -m "docs: add browser composition-only pattern to capability contracts"
```

---

## Task 5: Final Verification

### Step 1: Run full test suite

```bash
cd <worktree> && python -m pytest tests/ -q
```

Expected: Same pass/fail count as baseline (no regressions — this phase adds no Python code).

### Step 2: Verify all new YAML files

```bash
python -c "
import yaml
files = [
    'browser/behaviors/browser-capabilities.yaml',
    'recipes/setup-wizard.yaml',
]
for f in files:
    yaml.safe_load(open(f))
    print(f'{f}: OK')

# Verify bundle.md frontmatter
content = open('browser/bundle.md').read()
yaml.safe_load(content.split('---')[1])
print('browser/bundle.md: OK')
"
```

### Step 3: Verify file tree

```bash
find browser/ -type f | sort
```

Expected: ~20 files (3 bundle structure + ~17 skill files).

### Step 4: Show git log

```bash
git log --oneline feat/openclaw-migration-phase4-browser...HEAD~4
```

Expected: 4 commits (Tasks 1-4).

---

## Commit Sequence

| Order | Message | Files |
|-------|---------|-------|
| 1 | `feat(browser): satellite bundle structure — bundle.md, behavior, context` | 3 new |
| 2 | `feat(browser): commit agent-browser and webapp-testing skills` | ~17 new |
| 3 | `feat(browser): add browser configuration step to setup-wizard recipe` | 1 modified |
| 4 | `docs: add browser composition-only pattern to capability contracts` | 1 modified |
