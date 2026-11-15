# Image questions in format v2

This is a guide for converting a source image into a v2 question. Every question, including items that started as screenshots, must become a real v2 HTML or SVG type. Images are supporting media only, with alt text, and are never the question itself. The original image is always kept as a reference asset (`media[].original_asset` with sha256). Drafts only.

There is no `image_legacy` type. Do not invent a type that is not in `question_types.php`. Do not map an old image question to `image_based_choice` as a shortcut. Pick the right interactive type from the registry (`single_choice`, `multiple_select`, `yes_no_matrix`, `inline_dropdown`, `hotspot_single`, `active_screen`, and so on). `image_based_choice` remains in the site registry, but a migration must transcribe the item into that real type.

## Decision order

1. **Tables, text, and choices become HTML.** Transcribe the stem, table, list, or answer choices exactly into `learner.stem` as `format: "html"` (or `plain` only when no markup is needed). HTML must pass `sanitizer-allowlist.json`. Do not ship a screenshot of a table or of lettered choices when that content can be marked up. Check the transcription against the image with a deterministic method (OCR or pdftotext versus the text, table cell counts). Never guess a label or a cell.

2. **Diagrams become SVG only when they can be transcribed exactly.** Flow charts, simple architecture drawings, and labeled boxes may be SVG (`format: "svg"` on the stem, or `media` with `kind: "svg"`) when every label, line, and shape is captured with no guesswork. The SVG must pass the allow-list (no script, no foreignObject, no `on*` attributes, fragment-only `href`). Interactivity stays in CertPassly components (hotspot regions, and so on). Do not run author JavaScript. If an exact SVG cannot be produced, do not invent one; list the item for the owner.

3. **Photos and real UI screenshots stay as supporting raster images.** They are never the question itself. Use them as `learner.media` (or as the background of a hotspot / `active_screen` item) with alt text that describes the visible UI, not the answer. The interactive type is still the real registry type (for example `single_choice` with HTML choices, or `active_screen` with regions). Do not invent labels that are not in the image.

4. **Always keep the original image as a reference asset.** Even after you transcribe a table or redraw a diagram, store the source image sha256 (and href if you have one) in `original_asset`. Reviewers can compare the transcription to the source. Answer-area and marked-key images stay reviewer-only; do not put them in the learner payload. The original is not a license to put the answer in alt text.

5. **If the conversion is not exact, stop and list it.** `scripts/migrate_v1_to_v2.py` writes `cannot-convert.json` and `cannot-convert.md` with the question_key, the image path and sha256, the reason, and a suggested option. Anything that cannot be confirmed stays on that list for the owner.

## Alt text

Alt text is required on every image or SVG media asset. Write what a candidate who cannot see the image needs in order to attempt the item, without stating the keyed answer. If the official meaning of a control is not visible, say that it is not readable, and flag the item for review. Do not guess.

## What not to do

- Do not invent a type name that is not in `question_types.php`.
- Do not add `image_legacy`.
- Do not map old image questions to `image_based_choice` as a shortcut.
- Do not leave the question as an image.
- Do not put `is_correct` or answer letters only in the image.
- Do not use unsanitized HTML or SVG from an external authoring tool.
- Do not use `data:` image URLs unless `meta.allow_data_image` is true and `meta.data_image_justification` explains why an https or /storage file cannot be used. Default is deny. The site SVG sanitizer currently blocks all `data:` URIs.
- Do not drop the original file after a transcription.
- Do not guess content that OCR, pdftotext, or a cell count cannot confirm.
