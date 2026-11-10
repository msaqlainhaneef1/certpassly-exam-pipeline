# Troubleshooting

## install or pip

- `certpassly-pipeline --help` works after `pip install .` even if `reference/` is not next to the installed module.
- Running stages after a non-editable install needs `CERTPASSLY_SKILL_ROOT` pointing at this repo, or an editable install (`pip install -e .`).
- On Windows PowerShell use `install.ps1` and `.\.venv\Scripts\Activate.ps1`. Bash examples in the README are for Linux, macOS or Git Bash.

## Zip will not open

A zip sent through chat may not extract on Windows. Copy it to the Desktop (or another normal folder) and unzip from there.

## poppler / tesseract

The extract stage needs `pdftohtml` from poppler. Image-only items may use tesseract later. `install.sh` and `install.ps1` report what is missing. On Windows, add poppler's `Library\bin` folder to PATH and restart the shell.

## validate or check_bank failed

Read `out/<exam>/VALIDATION.md` and the `run.log` line for that stage. Typical causes:

- Official fact missing a saved source or a quote
- Cover-page duration or pass mark used in the simulator
- Typographic dash or a banned term in prose or a shared block
- Shared blocks over the configured share of a page
- Meta title or description outside 50-60 / 140-160
- Course schema on the practice-test page
- Missing `page_meta_extras.csv`

## Pages do not match a previous package

`page_prose.json` may include a full cached `body_html` for a frozen package. If you add `shared_keys` or `{{shared:...}}` markers, those are inserted and the HTML will change. That is expected for new exams.

## Catalog and Drive disagree

Sheet versus Drive mismatches go to `review.csv`. Do not invent a missing file or silently drop an extra one.

## Owner PDF will not split

See `extracted/layout.json` and `extracted/unparsed.json`. Image-only pages need the visual / author stage. VCE and other binary files are skipped at intake, not by the PDF extractor.

## Network

Use `--offline` once sources are saved. The tests force a dead proxy (`http://127.0.0.1:9`) so a missed offline flag cannot phone home.
