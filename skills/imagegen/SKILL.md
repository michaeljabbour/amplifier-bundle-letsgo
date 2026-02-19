---
name: imagegen
version: 1.0.0
description: >-
    Image generation and editing via the OpenAI Image API. Use when the user
    asks to generate or edit images (generate image, edit/inpaint/mask,
    background removal or replacement, transparent background, product shots,
    concept art, covers, or batch variants). Requires OPENAI_API_KEY.
---

# Image Generation Skill

Generate or edit images for project assets (website heroes, game art, UI mockups, product mockups, wireframes, logos, photorealistic images, infographics). Defaults to `gpt-image-1.5` and the OpenAI Image API.

## When to Use

- Generate a new image (concept art, product shot, cover, website hero)
- Edit an existing image (inpainting, masked edits, lighting/weather transforms, background replacement, object removal, compositing, transparent background)
- Batch runs (many prompts, or many variants across prompts)

## Decision Tree: generate vs edit vs batch

- If the user provides an input image (or says "edit/retouch/inpaint/mask/translate/localize/change only X") -> **edit**
- Else if the user needs many different prompts/assets -> **generate-batch**
- Else -> **generate**

## Workflow

1. Decide intent: generate vs edit vs batch (see decision tree above).
2. Collect inputs up front: prompt(s), exact text (verbatim), constraints/avoid list, and any input image(s)/mask(s). For multi-image edits, label each input by index and role; for edits, list invariants explicitly.
3. If batch: write a temporary JSONL under `tmp/` (one job per line), run once, then delete the JSONL.
4. Augment prompt into a short labeled spec (structure + constraints) without inventing new creative requirements.
5. Run via the OpenAI Python SDK (`openai` package) -- `client.images.generate(...)` or `client.images.edit(...)`.
6. For complex edits/generations, inspect outputs and validate: subject, style, composition, text accuracy, and invariants/avoid items.
7. Iterate: make a single targeted change (prompt or mask), re-run, re-check.
8. Save/return final outputs and note the final prompt + flags used.

## Commands (Python SDK)

### Generate

```python
from openai import OpenAI
client = OpenAI()

result = client.images.generate(
    model="gpt-image-1.5",
    prompt="<augmented prompt>",
    size="1024x1024",       # or 1536x1024, 1024x1536, auto
    quality="high",         # low, medium, high, auto
    background="auto",      # auto, transparent, opaque
    n=1,
)
# result.data[0].url or result.data[0].b64_json
```

### Edit

```python
result = client.images.edit(
    model="gpt-image-1.5",
    image=open("input.png", "rb"),
    mask=open("mask.png", "rb"),   # optional
    prompt="<edit prompt with invariants>",
    size="1024x1024",
    quality="high",
)
```

### Batch (JSONL)

Write one JSON object per line with `prompt`, `size`, `quality` fields. Process sequentially or with async calls.

## Dependencies

Prefer `uv` for dependency management:

```bash
uv pip install openai pillow
```

If `uv` is unavailable:

```bash
python3 -m pip install openai pillow
```

## Environment

- `OPENAI_API_KEY` must be set for live API calls.
- If the key is missing, instruct the user to create one at https://platform.openai.com/api-keys and set it as an environment variable.
- Never ask the user to paste the full key in chat.

## Defaults and Rules

- Use `gpt-image-1.5` unless the user explicitly asks for `gpt-image-1-mini` or prefers cheaper/faster.
- Assume the user wants a new image unless they explicitly ask for an edit.
- Require `OPENAI_API_KEY` before any live API call.
- Use the OpenAI Python SDK (`openai` package) for all API calls; do not use raw HTTP.
- If results are unsatisfactory, iterate with small targeted prompt changes; only ask a question if a missing detail blocks success.

## Prompt Augmentation

Reformat user prompts into a structured, production-oriented spec. Only make implicit details explicit; do not invent new requirements.

**Template** (include only relevant lines):

```
Use case: <taxonomy slug>
Asset type: <where the asset will be used>
Primary request: <user's main prompt>
Scene/background: <environment>
Subject: <main subject>
Style/medium: <photo/illustration/3D/etc>
Composition/framing: <wide/close/top-down; placement>
Lighting/mood: <lighting + mood>
Color palette: <palette notes>
Materials/textures: <surface details>
Quality: <low/medium/high/auto>
Input fidelity (edits): <low/high>
Text (verbatim): "<exact text>"
Constraints: <must keep/must avoid>
Avoid: <negative constraints>
```

**Augmentation rules:**
- Keep it short; add only details the user already implied or provided.
- Always classify into a taxonomy slug and tailor constraints/composition/quality to that bucket.
- For edits, explicitly list invariants ("change only X; keep Y unchanged").
- If any critical detail is missing and blocks success, ask a question; otherwise proceed.

## Use-Case Taxonomy (exact slugs)

### Generate

| Slug | Description |
|------|-------------|
| `photorealistic-natural` | Candid/editorial lifestyle scenes with real texture and natural lighting |
| `product-mockup` | Product/packaging shots, catalog imagery, merch concepts |
| `ui-mockup` | App/web interface mockups that look shippable |
| `infographic-diagram` | Diagrams/infographics with structured layout and text |
| `logo-brand` | Logo/mark exploration, vector-friendly |
| `illustration-story` | Comics, children's book art, narrative scenes |
| `stylized-concept` | Style-driven concept art, 3D/stylized renders |
| `historical-scene` | Period-accurate/world-knowledge scenes |

### Edit

| Slug | Description |
|------|-------------|
| `text-localization` | Translate/replace in-image text, preserve layout |
| `identity-preserve` | Try-on, person-in-scene; lock face/body/pose |
| `precise-object-edit` | Remove/replace a specific element (incl. interior swaps) |
| `lighting-weather` | Time-of-day/season/atmosphere changes only |
| `background-extraction` | Transparent background / clean cutout |
| `style-transfer` | Apply reference style while changing subject/scene |
| `compositing` | Multi-image insert/merge with matched lighting/perspective |
| `sketch-to-render` | Drawing/line art to photoreal render |

## Examples

### Generation example (hero image)

```
Use case: stylized-concept
Asset type: landing page hero
Primary request: a minimal hero image of a ceramic coffee mug
Style/medium: clean product photography
Composition/framing: centered product, generous negative space on the right
Lighting/mood: soft studio lighting
Constraints: no logos, no text, no watermark
```

### Edit example (invariants)

```
Use case: precise-object-edit
Asset type: product photo background replacement
Primary request: replace the background with a warm sunset gradient
Constraints: change only the background; keep the product and its edges unchanged; no text; no watermark
```

## Prompting Best Practices

- Structure prompt as scene -> subject -> details -> constraints.
- Include intended use (ad, UI mock, infographic) to set the mode and polish level.
- Use camera/composition language for photorealism.
- Quote exact text and specify typography + placement.
- For tricky words, spell them letter-by-letter and require verbatim rendering.
- For multi-image inputs, reference images by index and describe how to combine them.
- For edits, repeat invariants every iteration to reduce drift.
- Iterate with single-change follow-ups.
- For latency-sensitive runs, start with `quality=low`; use `quality=high` for text-heavy or detail-critical outputs.
- For strict edits (identity/layout lock), consider `input_fidelity=high`.
- If results feel "tacky", add a brief "Avoid:" line (stock-photo vibe, cheesy lens flare, oversaturated neon, harsh bloom, clutter) and specify restraint ("editorial", "premium", "subtle").

## Output Conventions

- Use `tmp/imagegen/` for intermediate files (e.g., JSONL batches); delete when done.
- Write final artifacts under `output/imagegen/` when working in a project.
- Use descriptive, stable filenames.

## Tips

- Always classify into a taxonomy slug before augmenting -- it guides composition, quality, and constraint choices
- For batch jobs, use JSONL to keep runs reproducible and atomic
- When editing, always list invariants explicitly to prevent drift
- Start with `quality=low` for rapid iteration, switch to `quality=high` for final output
- The `background=transparent` option is useful for assets that will be composited later
