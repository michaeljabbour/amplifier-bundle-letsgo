---
name: skill-creator
version: 1.0.0
description: >-
    Meta-skill for creating new Amplifier skills. Use when the user wants to
    create a new skill (or update an existing skill) that extends agent
    capabilities with specialized knowledge, workflows, or tool integrations.
    Covers skill anatomy, progressive disclosure, creation process, and design
    patterns for the Amplifier skill system.
# Skill Creator

Guide for creating effective Amplifier skills -- modular, self-contained packages that extend agent capabilities with specialized knowledge, workflows, and tools.

## About Skills

Skills are modular packages that extend an Amplifier agent's capabilities by providing specialized knowledge, workflows, and tools. They transform a general-purpose agent into a specialized one equipped with procedural knowledge that no model can fully possess.

### What Skills Provide

1. **Specialized workflows** -- Multi-step procedures for specific domains
2. **Tool integrations** -- Instructions for working with specific file formats or APIs
3. **Domain expertise** -- Project-specific knowledge, schemas, business logic
4. **Bundled resources** -- Scripts, references, and assets for complex and repetitive tasks

## Core Principles

### Concise is Key

The context window is a shared resource. Skills share it with the system prompt, conversation history, other skills' metadata, and the actual user request.

**Default assumption: the agent is already very smart.** Only add context the agent doesn't already have. Challenge each piece of information: "Does the agent really need this explanation?" and "Does this paragraph justify its token cost?"

Prefer concise examples over verbose explanations.

### Set Appropriate Degrees of Freedom

Match the level of specificity to the task's fragility and variability:

- **High freedom (text-based instructions)**: Multiple approaches are valid, decisions depend on context.
- **Medium freedom (pseudocode or scripts with parameters)**: A preferred pattern exists, some variation is acceptable.
- **Low freedom (specific scripts, few parameters)**: Operations are fragile, consistency is critical, a specific sequence must be followed.

Think of the agent as exploring a path: a narrow bridge with cliffs needs specific guardrails (low freedom), while an open field allows many routes (high freedom).

## Anatomy of a Skill

Every skill consists of a required `SKILL.md` file and optional bundled resources:

```
skill-name/
+-- SKILL.md (required)
|   +-- YAML frontmatter (required)
|   |   +-- skill:
|   |       +-- name: (required)
|   |       +-- version: (required)
|   |       +-- description: (required)
|   +-- Markdown instructions (required)
+-- Bundled Resources (optional)
    +-- scripts/          - Executable code (Python/Bash/etc.)
    +-- references/       - Documentation loaded into context on demand
    +-- assets/           - Files used in output (templates, icons, fonts, etc.)
```

### SKILL.md (required)

**Frontmatter** (YAML): Contains `skill.name`, `skill.version`, and `skill.description` fields. The description serves as the trigger mechanism -- agents read it to decide when to activate the skill. Be clear and comprehensive about what the skill does and when to use it.

```yaml
name: my-skill
version: 1.0.0
description: >-
    One-line description of what this skill does and when to use it.
    Include specific triggers and contexts.
---
```

**Body** (Markdown): Instructions and guidance for using the skill. Only loaded AFTER the skill triggers.

### Bundled Resources (optional)

#### Scripts (`scripts/`)

Executable code for tasks requiring deterministic reliability or that are repeatedly rewritten.

- **When to include**: Same code is rewritten repeatedly, or deterministic reliability is needed
- **Benefits**: Token efficient, deterministic, can be executed without loading into context
- **Example**: `scripts/rotate_pdf.py` for PDF rotation tasks

#### References (`references/`)

Documentation loaded into context on demand to inform the agent's process.

- **When to include**: For documentation the agent should reference while working
- **Examples**: API docs, database schemas, domain knowledge, company policies
- **Best practice**: If files are large (>10k words), include grep search patterns in SKILL.md
- **Avoid duplication**: Information should live in either SKILL.md or references, not both

#### Assets (`assets/`)

Files not loaded into context but used in the output the agent produces.

- **When to include**: When the skill needs files used in final output
- **Examples**: Templates, images, icons, boilerplate code, fonts, sample documents

### What NOT to Include

Do not create extraneous documentation files: README.md, INSTALLATION_GUIDE.md, CHANGELOG.md, etc. A skill should only contain what an agent needs to do the job.

## Progressive Disclosure Design Principle

Skills use a three-level loading system to manage context efficiently:

| Level | Content | Token Budget | When Loaded |
|-------|---------|-------------|-------------|
| 1 | Metadata (name + description) | ~100 tokens | Always in context |
| 2 | SKILL.md body | ~1-5k tokens | When skill triggers |
| 3 | Bundled resources (scripts/references/assets) | Unlimited | On demand by agent |

### Progressive Disclosure Patterns

Keep SKILL.md body under 500 lines. Split content into separate files when approaching this limit. When splitting, reference files from SKILL.md with clear descriptions of when to read them.

**Pattern 1: High-level guide with references**

```markdown
# PDF Processing

## Quick start
Extract text with pdfplumber: [code example]

## Advanced features
- **Form filling**: See [references/forms.md](references/forms.md) for complete guide
- **API reference**: See [references/api.md](references/api.md) for all methods
```

The agent loads references only when needed.

**Pattern 2: Domain-specific organization**

```
bigquery-skill/
+-- SKILL.md (overview and navigation)
+-- references/
    +-- finance.md (revenue, billing metrics)
    +-- sales.md (opportunities, pipeline)
    +-- product.md (API usage, features)
```

When a user asks about sales metrics, the agent only reads `sales.md`.

**Pattern 3: Variant-specific organization**

```
cloud-deploy/
+-- SKILL.md (workflow + provider selection)
+-- references/
    +-- aws.md (AWS deployment patterns)
    +-- gcp.md (GCP deployment patterns)
    +-- azure.md (Azure deployment patterns)
```

**Guidelines:**
- Avoid deeply nested references -- keep references one level deep from SKILL.md
- For files longer than 100 lines, include a table of contents at the top

## Skill Creation Process

1. **Understand** the skill with concrete examples
2. **Plan** reusable skill contents (scripts, references, assets)
3. **Initialize** the skill directory structure
4. **Edit** the skill (implement resources and write SKILL.md)
5. **Package** the skill for distribution
6. **Iterate** based on real usage

### Step 1: Understand the Skill

Clearly understand concrete examples of how the skill will be used. Ask:

- "What functionality should this skill support?"
- "Can you give examples of how it would be used?"
- "What would a user say that should trigger this skill?"

Conclude when there is a clear sense of the functionality the skill should support.

### Step 2: Plan Reusable Contents

Analyze each example by considering:

1. How to execute the example from scratch
2. What scripts, references, and assets would help when executing repeatedly

**Examples:**
- PDF rotation -> `scripts/rotate_pdf.py`
- Frontend webapp building -> `assets/hello-world/` template
- BigQuery queries -> `references/schema.md` documenting table schemas

### Step 3: Initialize the Skill

Create the skill directory structure:

```bash
mkdir -p skills/<skill-name>/{scripts,references,assets}
```

Create the `SKILL.md` with proper frontmatter:

```yaml
name: <skill-name>
version: 1.0.0
description: >-
    <Comprehensive description of what the skill does and when to use it.>
# <Skill Name>

<Instructions and guidance for using the skill.>
```

### Step 4: Edit the Skill

When editing, remember the skill is created for another agent instance to use. Include information that is beneficial and non-obvious.

**Writing guidelines:**
- Use imperative/infinitive form
- Include "when to use" information in the frontmatter description, not the body
- The body is only loaded after triggering, so "When to Use" sections in the body serve as reference, not as triggers

**Frontmatter description tips:**
- Include both what the skill does and specific triggers/contexts
- Example: "Image generation and editing via OpenAI Image API. Use when the user asks to generate or edit images (generate, edit/inpaint/mask, background removal, product shots, concept art, covers, or batch variants)."

### Step 5: Package the Skill

Place the completed skill directory under the bundle's `skills/` directory. The skill is available to agents that include the bundle.

For standalone distribution, package as a `.skill` file (zip with .skill extension):

```bash
cd skills/ && zip -r ../<skill-name>.skill <skill-name>/
```

### Step 6: Iterate

After testing the skill on real tasks:

1. Use the skill on real tasks
2. Notice struggles or inefficiencies
3. Identify how SKILL.md or bundled resources should be updated
4. Implement changes and test again

## Design Patterns for Amplifier Skills

### Delegate-Friendly Skills

Write skills so they work well when executed by sub-agents via Amplifier's delegate mechanism. Keep instructions self-contained so a delegated agent can operate without additional context.

### Recipe-Integrated Skills

Skills that pair with Amplifier recipes should document:
- Which recipe steps they support
- What context variables they expect
- What outputs they produce for downstream steps

### Gateway-Aware Skills

Skills that interact with the letsgo gateway (channels, scheduling, pairing) should reference the gateway module paths and data models explicitly. See the `schedule` and `send-user-message` skills as examples.

## Reference

- agentskills.io specification for portable skill format
- Amplifier bundle `skills/` directory for skill discovery and loading

## Tips

- Frontmatter description is the most important part -- it controls when the skill activates
- Keep SKILL.md body lean; move detailed content to `references/`
- Test scripts by actually running them before packaging
- Delete example/placeholder files that aren't needed
- One level of reference depth is enough -- avoid nested reference chains
- Challenge every paragraph: "Does this justify its token cost?"
