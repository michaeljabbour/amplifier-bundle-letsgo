---
skill:
  name: canvas-design
  version: 1.0.0
  description: Guide for using the canvas visual workspace effectively
  tags:
    - canvas
    - visualization
    - design
---

# Canvas Design Guide

## Content Type Selection

Choose the right content type for your visualization:

| Content Type | Best For | Content Format |
|-------------|----------|----------------|
| `chart` | Data visualization, graphs, plots | Vega-Lite JSON spec |
| `html` | Rich formatted content, interactive widgets | HTML string |
| `svg` | Diagrams, icons, custom graphics | SVG markup |
| `markdown` | Documentation, formatted text, mixed content | Markdown text |
| `code` | Source code, configuration files, logs | Plain text |
| `table` | Tabular data, comparison tables, results | JSON array of objects |

## Vega-Lite Charts

For charts, provide a complete Vega-Lite spec:

```json
{
  "$schema": "https://vega-lite.github.io/schema/v5.json",
  "data": {"values": [{"x": 1, "y": 2}, {"x": 2, "y": 4}]},
  "mark": "line",
  "encoding": {
    "x": {"field": "x", "type": "quantitative"},
    "y": {"field": "y", "type": "quantitative"}
  }
}
```

## Update-in-Place

Use the `id` parameter to update existing content:

1. First push: `canvas_push(content_type="chart", content=spec, id="sales-chart", title="Sales")`
2. Update: `canvas_push(content_type="chart", content=new_spec, id="sales-chart", title="Sales (Updated)")`

The item in the sidebar updates in place with a brief flash animation.

## Table Data Format

Tables expect a JSON array of objects. All keys become column headers:

```json
[
  {"Name": "Alice", "Score": 95, "Grade": "A"},
  {"Name": "Bob", "Score": 87, "Grade": "B+"},
  {"Name": "Carol", "Score": 92, "Grade": "A-"}
]
```

## Gateway Configuration

Add a canvas channel to `~/.letsgo/gateway/config.yaml`:

```yaml
channels:
  - name: canvas
    type: canvas
    config:
      host: localhost
      port: 8080
```

Install the channel package: `pip install letsgo-channel-canvas`
