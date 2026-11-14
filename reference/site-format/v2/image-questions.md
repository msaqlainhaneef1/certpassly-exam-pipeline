# Image question guide (question format v2)

Use this guide when you turn an owner PDF, a screenshot, or a diagram into a v2 question. The original image is always kept as a reference asset (`media[].original_asset` with sha256). Drafts only.

`image_legacy` is a requested compatibility type. It is **not** in `config/question_types.php`. The v2 enum does not add it. See `registry-mismatch.json`. Until the site registry adds a key, or until you map the item to an existing key such as `image_based_choice`, a file with `"type": "image_legacy"` fails validation as a registry mismatch.

## Decision order

1. **Tables, text, and choices become HTML (or plain text).** If the item is a table, a list, a short paragraph, or a set of answer choices that you can transcribe exactly, put that content in `learner.stem` as `format: "plain"` or `format: "html"`. HTML must pass `sanitizer-allowlist.json`. Do not ship a screenshot of a table when the table can be marked up.

2. **Diagrams become SVG only when they can be transcribed exactly.** Flow charts, simple architecture drawings, and labeled boxes may be SVG (`format: "svg"` on the stem, or `media` with `kind: "svg"`) when every label, line, and shape is captured with no guesswork. The SVG must pass the allow-list (no script, no foreignObject, no `on*` attributes, fragment-only `href`). Interactivity stays in CertPassly components (hotspot regions, and so on). Do not run author JavaScript.

3. **Photos and real UI screenshots stay as raster images.** Use an existing registry type: `image_based_choice` for a photo or UI shot with choices, or `hotspot_single` / `hotspot_multi` / `active_screen` when the learner clicks a region. Transcribe alt text that describes the visible UI, not the answer. Do not invent labels that are not in the image.

4. **Always keep the original image as a reference asset.** Even after you transcribe a table or redraw a diagram, store the source image sha256 (and href if you have one) in `original_asset`. Reviewers can compare the transcription to the source. The original may be `reviewer_only` on the site. It is not a license to put the answer in alt text.

## Alt text

Alt text is required on every image or SVG media asset. Write what a candidate who cannot see the image needs in order to attempt the item, without stating the keyed answer. If the official meaning of a control is not visible, say that it is not readable, and flag the item for review. Do not guess.

## What not to do

- Do not add `image_legacy` to the type enum just to make a file pass.
- Do not put `is_correct` or answer letters only in the image.
- Do not use unsanitized HTML or SVG from an external authoring tool.
- Do not use `data:` image URLs unless `meta.allow_data_image` is true and `meta.data_image_justification` explains why an https or /storage file cannot be used. Default is deny. The site SVG sanitizer currently blocks all `data:` URIs.
- Do not drop the original file after a transcription.
