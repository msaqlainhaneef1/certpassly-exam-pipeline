---
name: certpassly-exam-pipeline
description: >-
  Build site-ready CertPassly exam catalog pages and question-import files from
  official vendor sources and owner PDFs. Use when adding a vendor,
  certification or exam, importing a question bank, or running the exam
  pipeline. Scripts first. The default path is technical only (PDF to the site
  v2 exam file, no AI). Research, page prose and explanations are a separate
  command. No site-repo or GitHub on the run path.
---
# CertPassly exam pipeline

Scripts-first skill for draft, site-ready exam pages and question-import files. Official vendor sources plus owner PDFs in; a site v2 exam file, workbook CSVs, simulator settings, page JSON and a validation report out.

Current package version is `1.2.0`. **Read [reference/lessons-learned.md](reference/lessons-learned.md) before every run.** The lessons below are the short form of that file. Full commands, the run folder layout, the fidelity gate, the 15 Nov 2026 PDF results and the push flow are in [README.md](README.md) and [HANDOVER.md](HANDOVER.md). Config guides: [docs/question-type-rules.md](docs/question-type-rules.md), [docs/ocr.md](docs/ocr.md), [docs/fidelity.md](docs/fidelity.md).

## Top rules (repeat these)

1. Re-read the latest owner rules and `pipeline.yaml` before each stage. Rules have changed mid-run.
2. Official vendor brands, product names, certification titles and exam codes are required. CertPassly is the site brand.
3. Never use seller or competitor brands, social links, phone numbers, emails, or "free update" lines. Never use typographic dashes.
4. Questions come only from owner PDFs. Exact question types are never merged or guessed.
5. Never trust cover-page exam facts in an owner file. Duration, pass mark, languages and weights come from a saved official page (URL, sha256, quote). If the vendor does not publish a value, say so.
6. Do not drop a delivery partner the vendor still names.
7. VCE and other binary files are skipped and listed in REVIEW.md. Image-only items are flagged, not guessed. The fidelity gate holds anything it cannot confirm.
8. Flagged keys are never changed. On the technical path, a key must come from the PDF text or from two agreeing pixel methods, and it must map to existing ids. It is never inferred. On the later research path, items with no owner key are keyed only from saved OFFICIAL vendor pages (status unverified, reviewer needed) or flagged `answer_not_found` (draft, excluded from scoring).
9. Sheet versus Drive mismatches go to `review.csv`.
10. Pages stay draft. No Course schema on the practice-test page. Twitter / og:image / last-checked go in `page_meta_extras.csv`.
11. Batch AI. The only AI stage is `author`, and it is not on the default path. Research uses a vendor adapter first; AI may fill only listed official gaps, each with a quote.
12. This pipeline never reads the site application, artisan or GitHub. It reads `reference/site-format/` (v1 workbooks, and the site v2 exam schema).

## When to use

- A new vendor, certification or exam must be prepared for the catalog.
- An owner question PDF must become a site v2 exam file or an importable bank.
- You need to rerun validation or rebuild pages after official facts change.

## Two-part workflow and install

See the README for Git, pip and zip install (`install.sh` / `install.ps1`), including Linux `apt-get` and Windows PowerShell install of poppler and tesseract, and the `TESSERACT_DIR` setting.

Part 1 is technical and is the default. Scripts only: PDF to the site v2 exam file. No web, no AI, no explanations.

```bash
certpassly-pipeline --help
certpassly-pipeline --list-stages
certpassly-pipeline --exam EXAM-CODE --root /path/to/workspace --offline
```

Stages: intake, extract (local Tesseract OCR), export (site v2 plus the fidelity gate), validate_site, package.

Part 2 is `research` and `verify`: search, writing and AI.

```bash
certpassly-pipeline research --exam EXAM-CODE --root /path/to/workspace --offline
certpassly-pipeline verify --exam EXAM-CODE --root /path/to/workspace --offline
```

Also: `--vendor SLUG`, `--all`, `--batch`, `--stage NAME`, `--date YYYY-MM-DD`, `--force`.

If the zip does not open from a chat window, copy it to the Desktop and unzip there.

The fidelity gate (`config/fidelity.json` and `config/ocr.json`) exports a question only when word coverage is 100 percent with no extra words, dual OCR agrees at or above 90 per word and 95 overall, exactly one type rule matches and agrees with the key shape, and the answer key comes from text or two agreeing pixel methods. Held items and per-question coverage are written to `export/fidelity.json` and `export/fidelity.md`. Read those files with `export/cannot-convert.json`. Do not infer a missing key or type.

## Stages

| Stage | AI? | Path | Role |
| --- | --- | --- | --- |
| intake | no | technical | Reads owner files from `owner-files/<CODE>/`, writes `out/<CODE>/intake/files.json` and `rights-confirmation.md`. PDFs are extracted; VCE and other binaries are skipped. Online, an empty owner folder can be filled from a public Drive link. Offline skips the download. |
| extract | no | technical | Splits the owner PDF (layout detected). Runs local Tesseract OCR. Writes `extracted/` (`split.json`, `ocr.json`, `visual_draft.json`, `layout.json`, `unparsed.json`, `raw.xml`) and `media/src/`. |
| export | no | technical | Builds `<CODE>.site-format.v2.json` from the extract, `catalog.csv` and the type rules. Runs the fidelity gate. Writes `export/` reports. No explanations. |
| validate_site | no | technical | Python schema checker, and the site PHP SchemaValidator when `CERTPASSLY_SITE_VALIDATOR` is set. |
| package | no | both | Zip the exam output. Vendor and certification pages are included when a research JSON exists. |
| catalog | no | research | Sheet to `catalog.csv` / `review.csv`. Official URL checks reuse saved copies. |
| sources | no | research | Finds and hashes official pages from `catalog.csv`. Reuse saved copies. |
| research | parser first | research | Writes `research/<vendor>/<CODE>.json` from the adapter. Every fact has source_id, url, sha256 and a verbatim quote, or "not published by the vendor". |
| answer_research | pick only | research | No-answer items: candidate official pages only. Non-official URLs are rejected. |
| author | YES | research | The AI stage. Batched: page prose, rewritten explanations, `bank_meta`, visual transcription where OCR fails. Does not invent questions or change stems, options or keys. |
| pages | no | research | Build exam pages from research + `page_prose`. |
| import | no | research | Workbook CSVs, `page_meta_extras.csv`, simulator settings. |
| bank | no | research | `questions.json`, question CSVs, media, REVIEW.md, CLEANUP-LOG.md. |
| validate | no | verify | Manifest, `validate.py`, `check_bank.py`. Exit 1 on a failed check. |

## Vendor adapters and type rules

`config/vendors.yaml` names the adapter for each vendor slug (`generic` or a module under `scripts/adapters/`). Do not add exam-specific branches in shared scripts. A new exam is a catalog row plus PDFs in `owner-files/<CODE>/`.

Type detection is table-driven in `config/question_type_rules.json`. Add a mutually exclusive rule there (`all`, `any`, `none`, `not_all`). The type must already be in the site registry. The fidelity gate holds the item if zero or more than one rule matches.

## Site-format

`reference/site-format/v1/` holds the 30 question types, CSV headers, simulator schema and page fields for the older workbook path.

The technical export uses site format v2. `reference/site-format/v2/question.schema.json` is a verbatim copy of the site schema from worktree commit `a3009daa5` (schema sha256 `da9331c562a0e08cd156cc5efe6181cb8910ec19c523ff83dc43687190dc728e`). Provenance is in `PROVENANCE.md`. To refresh it when the site changes, copy the schema again from a read-only site worktree, update the commit and sha256 in `PROVENANCE.md`, and re-run the validators. Do not edit the schema by hand. This skill does not change site code.

The exam header (vendor, certification, name, exam code) comes from `catalog.csv` only. Domain falls back to Unassigned until domains can come from the catalog.

## Quality

`validate_site` must pass on every exported question. On the later path, `validate.py` and `check_bank.py` must pass. Official brands only. No typographic dashes. Held items stay held until the owner or a safer extract can confirm them.

## Tests

`python -m unittest discover -s tests -v` (offline, no AI). CI runs it on Linux and Windows (`feat/**` and `main`) with 0 skipped tests.

- `tests/test_technical_path.py` covers type rules, local OCR, the technical exporter, and the default CLI stage list.
- `tests/test_fidelity.py` covers the fidelity gate.
- `tests/test_docs.py` checks the hand docs for typographic dashes and emoji.
- `tests/test_demo_end_to_end.py` builds two synthetic demo workspaces and runs `research` then `verify`.
- Try a demo: `python tests/demo_kit.py microsoft DEMO_DIR` then `certpassly-pipeline --exam DM-101 --root DEMO_DIR --offline --date 2026-11-11` for part 1, or `research` and `verify` for part 2.

## Limits

- The author stage is not a model call. Someone (or a separate batched job) must write the authoring files. Author is not on the default path.
- Generic official-page parsing will miss facts that are not stated clearly. Those become gaps, not guesses.
- Owner PDFs with unusual layouts, low OCR confidence, disagreeing OCR passes, uncertain pixel keys, or a stem that disagrees with the owner key are held in `export/cannot-convert.json`. They are not guessed.
- Drive download needs folders shared as "Anyone with the link".
- Rendering official JS pages needs `pip install -e ".[render]"` and `python -m playwright install chromium`.
- Official reference links are kept in the export. The site rejects them until vendor hosts are added to `SITE_FORMAT_LINK_DOMAINS`.
- A non-editable `pip install .` is enough for `--help`. Full runs need a clone (`pip install -e .`) or `CERTPASSLY_SKILL_ROOT`.
- This skill does not publish pages, change site code, or write to the database.
- `v1.2.0` is tagged on `main`. Push `main` and the tag from the owner's PC, via a git bundle. The box does not push. Do not force-push. Do not rewrite the tag.
