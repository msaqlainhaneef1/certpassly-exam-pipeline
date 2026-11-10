# CertPassly exam pipeline

Scripts-first skill for draft, site-ready exam pages and question-import files. Official vendor sources plus owner PDFs in; workbook CSVs, simulator settings, page JSON and a validation report out.

**Read [reference/lessons-learned.md](reference/lessons-learned.md) before every run.** The lessons below are the short form of that file.

## Top rules (repeat these)

1. Re-read the latest owner rules and `pipeline.yaml` before each stage. Rules have changed mid-run.
2. Official vendor brands, product names, certification titles and exam codes are required. CertPassly is the site brand.
3. Never use seller or competitor brands, social links, phone numbers, emails, or "free update" lines. Never use typographic dashes.
4. Questions come only from owner PDFs. Exact question types are never merged.
5. Never trust cover-page exam facts in an owner file. Duration, pass mark, languages and weights come from a saved official page (URL, sha256, quote). If the vendor does not publish a value, say so.
6. Do not drop a delivery partner the vendor still names.
7. VCE and other binary files are skipped and listed in REVIEW.md. Image-only items are flagged for a visual pass, not guessed.
8. Flagged keys are never changed. Items with no usable answer are held, not invented.
9. Sheet versus Drive mismatches go to `review.csv`.
10. Pages stay draft. No Course schema on the practice-test page. Twitter / og:image / last-checked go in `page_meta_extras.csv`.
11. Batch AI. The only AI stage is `author`. Research uses a vendor adapter first; AI may fill only listed official gaps, each with a quote.
12. This pipeline never reads the site application, artisan or GitHub. It reads `reference/site-format/` (version from `site_format_version`, default `v1`).

## When to use

- A new vendor, certification or exam must be prepared for the catalog.
- An owner question PDF must become an importable bank.
- You need to rerun validation or rebuild pages after official facts change.

## Install

See the README for Git, pip and zip instructions (`install.sh` / `install.ps1`, including Windows PowerShell). After install:

```bash
certpassly-pipeline --help
certpassly-pipeline --exam EXAM-CODE --root /path/to/workspace --offline
```

Also: `--vendor SLUG`, `--all`, `--batch`, `--stage NAME`, `--date YYYY-MM-DD`, `--list-stages`.

If the zip does not open from a chat window, copy it to the Desktop and unzip there.

## Stages

| Stage | AI? | Role |
| --- | --- | --- |
| catalog | no | Sheet to `catalog.csv` / `review.csv`. Official URL checks reuse saved copies. |
| intake | no | Inventory and download owner files, provenance, skip binaries. |
| sources | no | Fetch and hash official vendor pages. Reuse saved copies. |
| research | parser first | Vendor adapter fills research JSON. AI only for listed official gaps. |
| extract | no | Split the owner PDF (layout detected). Write `layout.json` and `unparsed.json`. |
| author | YES | The AI stage. Batched: original page prose, rewritten explanations, `bank_meta`, visual transcription where OCR fails. Does not invent questions or change stems, options or keys. `run_pipeline` only checks that the files exist. |
| pages | no | Build exam pages from research + `page_prose`. Insert shared sections by key. Skip vendor/cert pages when unchanged. |
| import | no | Workbook CSVs, `page_meta_extras.csv`, simulator settings. |
| bank | no | `questions.json`, question CSVs, media, REVIEW.md, CLEANUP-LOG.md. |
| validate | no | Manifest, `validate.py`, `check_bank.py`. Exit 1 on a failed check. |
| package | no | Zip the exam package plus shared vendor and certification pages. |

## Vendor adapters

`config/vendors.yaml` names the adapter for each vendor slug (`generic` or a module under `scripts/adapters/`). The generic adapter extracts duration, pass mark, question count, price, languages, delivery, prerequisites, renewal and domains/weights when they are clearly stated, and lists gaps otherwise. Do not add exam-specific branches in shared scripts.

## Shared sections

Reusable blocks under `shared/` (site, vendor, certification, question-type). Templates insert them by key. A block is written only if it does not already exist. A page may not take more than `shared_max_share` (default 40 percent) of its wording from shared blocks. See [reference/shared-sections.md](reference/shared-sections.md).

## Site-format

`reference/site-format/v1/` holds the 30 question types and aliases, CSV headers, simulator schema, page fields, slug/URL rules, allowed statuses, and sample import files. Bump or add a version folder; set `site_format_version` in `pipeline.yaml`. An artisan dry run is optional and only for someone who already has application access. It is not on the default path.

## Quality

`validate.py` and `check_bank.py` must pass. Lesson gates cover official versus cover facts, skipped VCE files, vendor brand, sidecar meta, owner-file provenance, delivery partner, shared-section share, and banned terms in shared blocks. Meta titles 50-60 characters; descriptions 140-160. Five sourced tables. JSON-LD: BreadcrumbList, credential, Course (study guide only), FAQPage (sourced answers only). No Review or Rating.

## Tests

`python -m unittest discover -s tests -v` (offline). The gold-package regression runs when `CERTPASSLY_GOLD` (or a local gold workspace) is present; those caches are not committed. A second dry run exercises a non-Microsoft exam path with a synthetic owner PDF and reports official-source gaps honestly.

## Limits

- The author stage is not a model call. Someone (or a separate batched job) must write the authoring files.
- Generic official-page parsing will miss facts that are not stated clearly. Those become gaps, not guesses.
- Owner PDFs with unusual layouts may leave items in `unparsed.json`.
- A non-editable `pip install .` is enough for `--help`. Full runs need a clone (`pip install -e .`) or `CERTPASSLY_SKILL_ROOT`.
- This skill does not publish pages, change site code, or write to the database.
