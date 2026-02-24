# Canvas Wire Format

The JSON envelope is the shared contract between `tool-canvas` (producer) and `CanvasChannel` (consumer). Both components sit on opposite sides of the `DisplaySystem` protocol boundary but must agree on this structure.

## Envelope Schema

```json
{
  "content_type": "chart",
  "content": "<vega-lite-spec-or-html-or-svg-or-markdown>",
  "id": "chart-1",
  "title": "Monthly Revenue"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `content_type` | string | Yes | One of: `chart`, `html`, `svg`, `markdown`, `code`, `table` |
| `content` | string | Yes | The actual content (Vega-Lite JSON, HTML, SVG, markdown text, code, or JSON array for tables) |
| `id` | string | No | Stable identifier for update-in-place — same ID replaces previous content |
| `title` | string | No | Display title shown in the canvas sidebar |

## Transport

The envelope travels as a JSON string in `OutboundMessage.text`:

```
tool-canvas → json.dumps(envelope) → DisplaySystem.display(text, metadata)
             → OutboundMessage(text=json_string)
             → CanvasChannel.send(message) → json.loads(message.text)
```

The `DisplaySystem` is a transparent pipe — it routes but does not interpret the content. Content semantics live at the edges.

## Content Type Details

### `chart`
Content is a complete Vega-Lite specification as a JSON string. The canvas UI parses it and renders via `vega-embed`.

### `html`
Content is an HTML string rendered in a sandboxed iframe (`sandbox="allow-scripts"`).

### `svg`
Content is an SVG markup string injected as inline SVG.

### `markdown`
Content is a markdown string rendered via the `marked` library with `highlight.js` for code blocks.

### `code`
Content is a source code string rendered in a `<pre><code>` block with syntax highlighting.

### `table`
Content is a JSON string containing an array of flat objects. All keys become column headers, values become cells.

## Update-in-Place Semantics

When `id` is provided:
- If an item with the same `id` exists, it is replaced with the new content
- The item moves to the top of the sidebar (newest position)
- Connected WebSocket clients see a brief flash animation

When `id` is omitted:
- A random 8-character ID is generated
- A new item is created at the top of the sidebar

## WebSocket Message Format

The `CanvasChannel` pushes updates to connected browsers as JSON over WebSocket:

```json
{
  "type": "update",
  "id": "chart-1",
  "content_type": "chart",
  "content": "<vega-lite-spec>",
  "title": "Monthly Revenue"
}
```

## State Recovery

On WebSocket reconnection, the client fetches `GET /canvas/state` which returns:

```json
{
  "items": [
    {"id": "chart-1", "content_type": "chart", "content": "...", "title": "..."},
    {"id": "html-2", "content_type": "html", "content": "...", "title": null}
  ]
}
```

Items are ordered newest first.
