# Skills Awareness

LetsGo provides 21 domain expertise skills in 5 categories. Load on demand via `load_skill` — only metadata is in context until a skill is triggered.

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

**Delegate to specialist agents** when the task involves multiple related skills (e.g., branded slide deck needs `pptx` + `brand-guidelines` + `theme-factory`), or the skill has complex scripts and reference files.

**Load directly** when the task maps to a single skill with clear instructions, or you're already deep in implementation and need quick reference.
