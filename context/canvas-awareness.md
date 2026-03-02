# Canvas Capabilities

Visual workspace for displaying rich content via the `canvas_push` tool at `http://localhost:8080/canvas`.

## Content Types

- **chart** — Vega-Lite JSON specs rendered as interactive charts
- **html** — Arbitrary HTML rendered in a sandboxed iframe
- **svg** — Inline SVG graphics
- **markdown** — Rendered markdown with syntax-highlighted code blocks
- **code** — Syntax-highlighted code blocks
- **table** — Tabular data as HTML table (JSON array of objects)

## Parameters

`content_type` (required), `content` (required), `id` (optional, stable ID for in-place updates), `title` (optional, sidebar display title)

For complex visual design work, delegate to `letsgo:creative-specialist`.
