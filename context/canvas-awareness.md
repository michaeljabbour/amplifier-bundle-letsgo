# Canvas Capabilities

You have access to a visual workspace (canvas) for displaying rich content to the user.

## canvas_push Tool

Use the `canvas_push` tool to display visual content on the canvas web UI:

- **chart**: Vega-Lite JSON specs rendered as interactive charts
  - Content: Valid Vega-Lite JSON specification string
- **html**: Arbitrary HTML rendered in a sandboxed iframe
  - Content: HTML string
- **svg**: Inline SVG graphics
  - Content: SVG markup string
- **markdown**: Rendered markdown with syntax-highlighted code blocks
  - Content: Markdown text
- **code**: Syntax-highlighted code blocks
  - Content: Source code string
- **table**: Tabular data rendered as an HTML table
  - Content: JSON array of objects (e.g., `[{"name": "Alice", "score": 95}]`)

## Parameters

- `content_type` (required): One of chart, html, svg, markdown, code, table
- `content` (required): The content string
- `id` (optional): Stable identifier — use the same ID to update an existing item in-place
- `title` (optional): Display title shown in the sidebar

## Tips

- Use `id` when you want to update content (e.g., a chart that refreshes with new data)
- Omit `id` when pushing one-off content
- Charts work best with self-contained Vega-Lite specs (include `$schema`, `data`, `mark`, `encoding`)
- Tables expect a JSON array of flat objects — all keys become column headers
- The canvas web UI is at `http://localhost:8080/canvas` — tell the user to open it in their browser

## Fallback

If no canvas channel is connected, content is sent as text to the first available chat channel. The JSON envelope will appear as-is — this is expected behavior for users who haven't enabled the canvas.
