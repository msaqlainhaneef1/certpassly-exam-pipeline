# OCR settings

File: `config/ocr.json`.

Local Tesseract reads text out of images taken from the owner PDF. There is no cloud OCR and no AI. Settings in this file are general. Do not add per-exam branches.

## Extract fill (the `ocr.json` root)

These keys control how extract fills stems, choices, tables and matrix rows, and how it looks for answer marks:

- `engine`: `tesseract`
- `lang`: `eng`
- `psm`: page segmentation mode for the fill pass (default 3)
- `scale` and `dpi`: image scale and the raster DPI used when a page is rendered with `pdftoppm`
- `min_word_confidence` and `min_item_confidence` / `hold_below_confidence`: looser floors used while filling text (the fidelity gate applies its own, stricter floors)
- `extract_tools`: `pdftohtml`, `pdftoppm`, `pdfimages`
- `rasterize_pages_when_no_images`: render a page when the item has no images and no usable text
- `marker`, `highlight`, `checkbox`: pixel rules for dark marks, coloured highlights and checked boxes

Install hints live under `install.apt_packages`. On Linux: `sudo apt-get install -y poppler-utils tesseract-ocr tesseract-ocr-eng`. On Windows, install Poppler and Tesseract (Chocolatey or the UB Mannheim installer) and set `TESSERACT_DIR` if `tesseract.exe` is not on PATH. See the README.

## Fidelity block

The `fidelity` object in this file is merged with `config/fidelity.json`. It names the two OCR passes and the safe confidence floors:

- `min_word_confidence`: 90
- `min_overall_confidence`: 95
- `require_pass_agreement`: true
- `passes`: two entries, by default `psm` 3 with no preprocess, and `psm` 6 with a threshold preprocess

Both passes must agree on the normalised text. If they do not, or a word is below 90, or overall confidence is below 95, the question is held and the low words or the disagreement are written into the fidelity reason.

## How to tune safely

Prefer leaving the fidelity floors at 90 and 95. Safer changes:

- Raise `min_word_confidence` or `min_overall_confidence`.
- Keep `require_pass_agreement` true.
- Add a third pass only if you still require all passes to agree.
- Raise `dpi` or `scale` so the same thresholds see a sharper image (this is also a planned improvement: higher resolution page renders).

Less safe (will export unconfirmed text):

- Lowering the 90/95 floors
- Turning off pass agreement
- Treating a single pixel method as a key (that is a fidelity key setting, not an OCR fill setting)

Record a change in `CHANGELOG.md` and rerun the unit tests plus a real PDF before you trust a new threshold.
