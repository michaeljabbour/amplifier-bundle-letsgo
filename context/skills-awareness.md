# Skills Awareness

LetsGo provides 20 domain expertise skills organized in 5 categories.
Skills are loaded on demand via `load_skill` — only metadata (name + description)
is in context until a skill triggers.

## Skill Routing

| User intent | Load skill | Or delegate to |
|-------------|-----------|----------------|
| Create/edit Word documents | `docx` | `letsgo:document-specialist` |
| Create/edit PDFs | `pdf` | `letsgo:document-specialist` |
| Create/edit presentations | `pptx` | `letsgo:document-specialist` |
| Create/edit spreadsheets | `xlsx` | `letsgo:document-specialist` |
| Design posters, visual art | `canvas-design` | `letsgo:creative-specialist` |
| Generative/algorithmic art | `algorithmic-art` | `letsgo:creative-specialist` |
| Apply brand colors/fonts | `brand-guidelines` | `letsgo:creative-specialist` |
| Build web UI/components | `frontend-design` | `letsgo:creative-specialist` |
| Style slides/docs with themes | `theme-factory` | `letsgo:creative-specialist` |
| Create animated GIFs | `slack-gif-creator` | `letsgo:creative-specialist` |
| Build MCP servers | `mcp-builder` | — |
| Create HTML artifacts | `web-artifacts-builder` | — |
| Test web applications | `webapp-testing` | — |
| Co-author documents/proposals | `doc-coauthoring` | — |
| Write internal communications | `internal-comms` | — |
| Browser automation | `agent-browser` | — |
| Generate/edit images | `imagegen` | — |
| Schedule cron tasks | `schedule` | — |
| Send proactive messages | `send-user-message` | — |
| Create new skills | `skill-creator` | — |

## When to Delegate vs Load Directly

**Delegate to specialist agents** when:
- The task involves multiple related skills (e.g., "create a branded slide deck" needs `pptx` + `brand-guidelines` + `theme-factory`)
- The skill has complex scripts and reference files (office document skills)
- You want to keep the root session lean (context sink pattern)

**Load directly** when:
- The task maps to a single skill with clear instructions
- The skill is lightweight (no scripts, just guidance)
- You're already deep in implementation and need quick reference

## Document Skills (docx, pdf, pptx, xlsx)

These 4 skills share a common OOXML validation toolkit (`scripts/office/`) and
follow similar patterns: read/create/edit workflows with format-specific scripts.

**Key capabilities:**
- **docx**: Create with docx-js, edit XML directly, tracked changes, comments, images
- **pdf**: Read (pdfplumber), create (reportlab), merge/split/rotate (pypdf), fill forms, OCR
- **pptx**: Create with PptxGenJS, template-based editing, thumbnails, slide cleanup
- **xlsx**: Financial models, formulas, pandas + openpyxl workflows, LibreOffice recalc

**Dependencies**: Each skill has a `requirements.txt`. Install before first use:
```bash
pip install -r skills/<skill-name>/requirements.txt
```

**Shared toolkit**: `scripts/office/` in docx/pptx/xlsx contains OOXML validators,
XML helpers, and LibreOffice wrappers (auto-configured for sandboxed environments).

## Creative Skills

**Key capabilities:**
- **canvas-design**: PDF/PNG art using design philosophies. Includes 54 TTF fonts in `canvas-fonts/`
- **algorithmic-art**: p5.js generative art. Templates in `templates/` (viewer.html, generator_template.js)
- **brand-guidelines**: Anthropic brand colors and typography reference
- **frontend-design**: Production-grade web UI with anti-"AI slop" design principles
- **theme-factory**: 10 preset themes for styling any artifact. Theme definitions in `themes/*.md`
- **slack-gif-creator**: Animated GIFs optimized for Slack. Python modules in `core/` (gif_builder, frame_composer, easing, validators)

## Developer Skills

- **mcp-builder**: 4-phase MCP server development (Research → Implement → Review → Evaluate). Reference docs in `reference/`, evaluation scripts in `scripts/`
- **web-artifacts-builder**: Multi-component HTML artifacts (React + Tailwind + shadcn/ui). Shell scripts for init and bundling
- **webapp-testing**: Playwright-based web app testing. Server lifecycle management in `scripts/`, examples in `examples/`

## Communication Skills

- **doc-coauthoring**: 3-stage collaborative document workflow (Context Gathering → Refinement → Reader Testing)
- **internal-comms**: Format templates for status reports, newsletters, FAQs. Examples in `examples/`

## Operations Skills

- **agent-browser**: Browser automation CLI. Reference docs in `references/`, shell templates in `templates/`
- **imagegen**: OpenAI Image API (gpt-image-1.5). Reference docs in `references/`
- **schedule**: Cron job management through gateway CronScheduler
- **send-user-message**: Proactive outbound messaging through gateway channels
- **skill-creator**: Meta-skill for authoring new skills. Includes `scripts/init_skill.py`, `scripts/package_skill.py`, `scripts/quick_validate.py`
