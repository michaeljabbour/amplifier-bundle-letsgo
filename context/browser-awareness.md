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
