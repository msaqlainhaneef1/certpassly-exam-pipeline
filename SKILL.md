---
name: certpassly-exam-pipeline
description: >-
  Build site-ready CertPassly exam catalog pages and question-import files from
  official vendor sources and owner PDFs. Use when adding a vendor,
  certification or exam, importing a question bank, or running the exam
  pipeline. Scripts first; one batched AI author stage; no site-repo or GitHub
  on the run path.
---
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
| catalog | no | Sheet to `catalog.csv` / `review.csv`. Official URL checks reuse saved copies. With no sheet, an existing `catalog.csv` is kept. |
| intake | no | Reads owner files from `owner-files/<CODE>/` (or `paths.owner_files` in `pipeline.yaml`), writes `intake/files.json` (sha256, use) and `rights-confirmation.md` from `owner_rights_statement`. PDFs are extracted; VCE and other binaries are skipped. Drive download is a separate step (see Limits). |
| sources | no | Fetch and hash official vendor pages. Reuse saved copies. |
| research | parser first | Vendor adapter fills research JSON. AI only for listed official gaps. |
| extract | no | Split the owner PDF (layout detected). Write `layout.json` and `unparsed.json`. |
| author | YES | The AI stage. Batched: original page prose, rewritten explanations, `bank_meta`, visual transcription where OCR fails. Does not invent questions or change stems, options or keys. `run_pipeline` only checks that the files exist. |
| pages | no | Build exam pages from research + `page_prose`. Insert shared sections by key. Render the five sourced tables (key facts, objectives, study plan, vendor exams, certification requirements) from research when the prose has none. Skip vendor/cert pages when unchanged. |
| import | no | Workbook CSVs, `page_meta_extras.csv`, simulator settings. |
| bank | no | `questions.json`, question CSVs, media, REVIEW.md, CLEANUP-LOG.md. Items with no answer in the owner file are held, never keyed. Intake-skipped files are listed in REVIEW.md automatically. |
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

`python -m unittest discover -s tests -v` (offline, no AI). CI runs it on Linux and Windows with 0 skipped tests.

- `tests/test_demo_end_to_end.py` builds two synthetic demo workspaces with `tests/demo_kit.py` (one per adapter path: the Microsoft adapter and the generic adapter) and runs every default stage through the CLI with no manual step. Each demo PDF carries seller branding, a social link, a phone, an email and a free-update line (stripping is checked), six items (single choice, multiple select, Yes/No matrix, inline drop-down, one held image-only item, one held no-answer item) and a skipped VCE file.
- Try a demo yourself: `python tests/demo_kit.py microsoft DEMO_DIR` then `certpassly-pipeline --exam DM-101 --root DEMO_DIR --offline --date 2026-11-11` (generic path: profile `salesforce`, exam `Demo-Admn-101`).
- The gold-package regression on a real finished exam runs only when `CERTPASSLY_GOLD` points at a local gold workspace (real owner extracts are never committed). Without it, the regression is not collected, so it never shows as skipped.

## Limits

- The author stage is not a model call. Someone (or a separate batched job) must write the authoring files.
- Generic official-page parsing will miss facts that are not stated clearly. Those become gaps, not guesses.
- Owner PDFs with unusual layouts may leave items in `unparsed.json`.
- The intake stage does not download from Google Drive by itself. Put the owner files in `owner-files/<CODE>/` first (Drive download helpers live in `scripts/drive_inventory.py` and `scripts/provenance_scan.py`).
- The research JSON (`research/<vendor>/<CODE>.json`, vendor and certification files) is still written once per exam from the adapter output plus quoted gaps. The adapter checks it; it does not write it.
- JavaScript-rendered official pages (for example some vendor academy pages) return no text to a plain fetch. Save a rendered copy (browser) under `sources/<vendor>/` with its sha256 sidecar, or the adapter reports every fact as a gap.
- Tested on synthetic demo exams and the AB-730 gold rebuild. Real new exams (live Drive, live official pages, real authoring) have not been run with v1.0.2.
- A non-editable `pip install .` is enough for `--help`. Full runs need a clone (`pip install -e .`) or `CERTPASSLY_SKILL_ROOT`.
- This skill does not publish pages, change site code, or write to the database.
