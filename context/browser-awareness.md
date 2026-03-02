# Browser Capabilities

Three specialized browser agents are available via the LetsGo gateway. Delegate browser work to them rather than running `agent-browser` commands directly — the agents handle retry logic, snapshot lifecycle, and failure budgets.

## Available Agents

- **browser-operator** — General-purpose automation: navigate pages, fill forms, click buttons, extract data, take screenshots. The workhorse for any browser interaction.
- **browser-researcher** — Multi-page research: explore documentation, compare competitors, synthesize findings from multiple sites. Returns structured summaries with source citations.
- **visual-documenter** — Visual documentation: capture screenshots at multiple viewports, document UI flows step-by-step, create before/after comparisons for QA evidence.
