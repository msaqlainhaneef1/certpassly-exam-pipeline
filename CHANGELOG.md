# Changelog

## 1.2.0 (2026-11-11)

Writing work from the v1.2.0 plan (HANDOVER.md section 8), plus the fixes found by the first real run (Microsoft SC-900 from the owner Drive folder: 253 imported, 0 held).

### Owner rules

- Stems and options get spelling, grammar and punctuation fixes only. Never change meaning, the correct answer, or option order. Official vendor product names stay exact. Every change is logged in `text-fixes.json` and gated by the key and option-order identity check (validate 12n).
- The package zip never ships raw extracts or a denylist term. The package stage fails on a hit.

### Real-run fixes and gates

- Catalog: a sheet with nothing to review no longer crashes; `review.csv` is header only.
- Extract: a keyed answer image placed before an empty "Correct Answer:" line becomes the answer image.
- Extract: words whose fi/fl/ff/ffi/ffl glyph the PDF text layer lost are repaired when a gap is left (`scripts/text_repair.py`, `config/ligature_words.txt`).
- Research: exam length is never taken from the extra-time rule; discovery prefers the exam's own page and keeps links with a `#fragment`.
- Bank: DRAG DROP items become `drag_drop` (tiles as `left`, targets as `right`, key `pairs`). Validate 12f, 12g and 12h check them. Pages: unpublished languages, format and level render as "not published by the vendor".
- New stage `textfix` and `scripts/text_fixes.py`: spelling, grammar and punctuation fixes for stems and options. Script rules (lost ligature with no gap, repeated word, space before punctuation, double space) and author decisions (`authoring/text_fixes_decisions.json` for a/an and possible typos, plus `extra` fixes). Protected words: vendor terms on the saved official pages and capitalized words. Applied in the bank stage, logged in `text-fixes.json`, summarized in REVIEW.md and CLEANUP-LOG.md. New `text_fixes:` block in `config/pipeline.example.yaml`.
- Key identity gate: a digest of key letters, option ids in order, option count and the visual key per item, before and after text fixes. The bank stage refuses to apply a change that moves it; validate 12n recomputes it from `split.json` against `questions.json`.
- `suspect_lost_ligatures` lists words still missing a ligature in REVIEW.md for the owner; `[known_words]` keeps common words from being flagged.
- New `scripts/package_guard.py`: the package stage leaves out raw extracts (`package_exclude` in `pipeline.yaml`, plus any file under `extracted/` that still holds a removed seller line), ships `extracted/cleanups.redacted.json` and `PACKAGE-EXCLUDED.json`, then scans every file in the zip (nested archives, camelCase-glued brands) against `brand_denylist` and `contact_patterns`. Any hit fails the stage and removes the zip. `<zip>.scan.json` reports files and rule numbers, never the term.
- Tests: `tests/test_v120_real.py`.

### Writing brief and the check-then-fix loop

- New `reference/writing-brief.md`: plain English, short sentences, a summary of Google's people-first guidance, the banned AI-phrase list with bad and good examples, the check-then-fix loop, and the self-check.
- New `config/banned_ai_phrases.txt`: the banned AI-phrase list as data. A workspace can add `config/banned_ai_phrases.txt`. `banned_phrases` in `pipeline.yaml` are checked too.
- New stage `intent` and `scripts/search_intent.py`: builds `research/<vendor>/<CODE>.search-intent.json` from research facts only (main query per page, people-also-ask questions from official facts and recorded gaps, and which page answers each). It never invents a number. Topic labels from the optional `research/<vendor>/<CODE>.competitor-notes.json` are recorded as topics only, marked with official support. Labels that are long or name a banned brand are dropped.
- New stage `writing` and `scripts/check_writing.py`: flags banned AI phrases (vendor quotes found word for word on a saved official page are exempt), long sentences, typographic dashes, unsourced numbers, thin pages, reading grade, missed search-intent questions, invented numbers in the intent file, copied competitor wording (8 or more words), and unflagged parts rewritten during a fix round. Writes `writing-review.json`, `WRITING-REVIEW.md` (failed checks only), `writing-self-check.json`, and `authoring/writing_fix_request.json` (only the flagged parts). Shared blocks are checked once as their own part.
- `run_pipeline.py`: `intent` runs before author and pages (and is built on demand if missing); `writing` runs after pages, and a pages rebuild always runs the writing check again (the second check after a fix). The runner still never calls a model.
- `build_pages.py`: each page JSON carries its `search_intent` (main query and assigned questions). It never reads competitor notes.
- `validate.py`: optional check 19 (`writing.validate_gate: true`) requires a current, clean writing review. Competitor-notes files are inputs and are left out of the output scans.
- `build_bank.py`: open writing flags are listed in `REVIEW.md`.
- `shared/site/editorial-policy.json` 1.1.0: one 41-word sentence split into three short ones (found by the new long-sentence check).
- `config/pipeline.example.yaml`: new `writing:` block.
- Demo kit: each demo now has a synthetic competitor-notes file with a sentence that must never reach an output.
- Tests: `tests/test_v120.py` and fixtures in `tests/fixtures/v120/`. Demo keys and option order are unchanged.

## 1.1.5

- Fix Windows: `generic._load_sources`, the Microsoft adapter and `validate.py` now resolve saved-source `path` and `text_path` through a shared `fetch_sources.resolve_sidecar_paths` / `load_sidecar` helper (the same remap `find_saved` already used). A workspace copied from another machine no longer reads empty official pages, so research can find official skill weights without a hand-edited sidecar.
- Fix Windows: Poppler 25.07.0 `pdftohtml -xml` can emit unreliable `top` values (many distinct lines share the same coordinates; some early markers get a huge or flipped `top`). Sorting every element by `(page, top, left)` then put "QUESTION 1" after later items and dropped owner answer keys. The extractor now uses XML document order when tops look untrustworthy, still sorts by `(top, left)` when they are consistent (same-line answer letters), and normalises CRLF in the XML. Not exam- or vendor-specific.
- Tests: `tests/test_v115.py` (foreign absolute sidecar paths; collapsed/flipped tops; CRLF xml).


## 1.1.4

- Real Salesforce Data-Con-101 run finished through author (one batched pass: 65 short explanations and page prose), pages, import, bank, validate, check_bank and package. 65 questions imported, 0 held, 62/62 validate checks passed, check_bank 2841 passed / 0 failed.
- Fix validate check 02: official outlines that state a single weight as `Solution Positioning: 14%` (Salesforce and similar) now match, not only the range form `Name (min-max%)`.
- Fix key facts and simulator settings: when the vendor publishes a price or question count, use the official value and source. Previously the price cell always showed "not published by the vendor" and question count was hardcoded as a site choice. Check 12c now requires an official count when one is published, and site choice only when it is not.
- New `scripts/check_import_conformance.py` checks produced import files against `reference/site-format/v1` (CSV templates, question types, allowed statuses, simulator schema, including `key_source`, `verification_status`, `researched_unverified`, `answer_not_found`, and `scoring_excluded_question_keys`). This is not a live site-importer run.
- `simulator_settings.schema.json` now documents `scoring_excluded_question_keys` and `scoring_excluded_note`.
- Tests: `tests/test_v114.py` (weight wording, conformance of the new fields).


## 1.1.3

- Fix Windows: answer_research stored saved_path with backslashes; evidence paths are now always written with forward slashes so files are portable across OSes.

## 1.1.2

- Fix Windows: validate skip list for raw folders (extracted, media, answer_research) used forward slashes only, so the denylist scan flagged the stripped-text audit file on Windows.

## 1.1.1

- Fix Python 3.11 SyntaxError in build_bank.py REVIEW line (nested f-string quotes) that failed CI on all four jobs.

## 1.1.0 (2026-11-11)

- New owner rule: no-answer items are never held. New `answer_research` stage (`scripts/answer_research.py`): candidate official pages (research sources, listed URLs, site-restricted search on `official_domains`), saved with sha256, ranked matching lines, scripted region boxes for image items. One batched AI pick (`authoring/answer_research.json`) is re-verified by script (official domain, saved copy, verbatim quote, key fits). Imported as `researched_unverified` / `key_source=researched_official` / `verification_status=unverified`, `reviewer_needed`. No evidence: `answer_not_found`, draft, logged searched URLs, excluded from scoring (`scoring_excluded_question_keys` in simulator settings). New gates validate 12l/12m; check_bank exempts answer_not_found from key and region checks. Allowed statuses extended (`researched_unverified`, `answer_not_found`, `key_source`, `verification_status`): the site importer must accept them.
- AB-730 q089 (active_screen) now imported with key r2 "the Sources information icon" from learn.microsoft.com manage-public-web-access (confidence high, unverified).
- Drive download automated in intake (`scripts/drive_fetch.py`): public folder links from catalog.csv, subfolders, sha256 manifest, resume, clear errors. Offline skips it.
- Research JSON generated by script (`scripts/research_init.py`): official page discovery from catalog.csv + vendor patterns, quoted facts, "not published by the vendor" for the rest, `research/gaps.json`. Hand-written files are kept.
- JS-rendered official pages: `scripts/render_page.py` (optional extra `[render]`, Playwright) used when a plain fetch has too little text or the vendor sets `render: true`.
- Catalog: exam-specific labels moved from `build_catalog.py` to `config/catalog_overrides.json`; a grep gate test fails on exam literals in scripts.
- Fixes found on the real Data-Con-101 run: pass-mark line parsed as a domain; "maintainable" read as renewal; sidecar absolute paths broke copied workspaces; runner hid SystemExit messages.
- Tests: `tests/test_v110.py`; demo kits now exercise researched and answer_not_found items.

## 1.0.2 (2026-11-11)

Demo end-to-end runs on two synthetic exams (Microsoft adapter and generic adapter) found and fixed these defects:

- intake: the stage never built `intake/files.json`; it only told you to write it by hand. It now reads `owner-files/<CODE>/` (or `paths.owner_files`), hashes every file, marks PDFs extracted and VCE/binaries skipped, and writes `rights-confirmation.md` from `owner_rights_statement`.
- catalog: the default run failed with "Sheet not found" even when `catalog.csv` existed (the README quick start path). It now keeps the existing catalog when no sheet is given.
- pages: the five sourced tables were computed but never rendered to HTML, so any exam whose author prose had no hand-written tables failed check 11b. Tables are now rendered from research rows when the prose has none (prose that already has tables is unchanged, so the gold rebuild still matches).
- pages: an unpublished pass mark rendered as "None or higher". Unpublished facts now show "not published by the vendor".
- validate 01c: failed every exam whose vendor does not publish a pass mark. It now accepts an empty pass mark when research records the not-published reason.
- bank: an item with no answer in the owner file crashed the key-shape gate instead of being held. It is now held with the reason "no answer in the owner file; key not invented". A missing explanation now stops with a clear author-stage message instead of a KeyError.
- bank: `cover_facts_conflict` given as a list crashed REVIEW.md; REVIEW.md also hardcoded "All 41 image-based items" from the first exam. Both fixed; the count is computed.
- bank: files skipped at intake (VCE) are listed in REVIEW.md even if `bank_meta.skipped_files` omits them. The bank source is the first extracted PDF, not simply the first file.
- import: crashed when a certification research file had no `last_updated`.
- generic adapter: "105 minutes" was never read (regex required `minute\b`), "Languages:" with a capital L was never read, a single language was ignored, and HTML tags were removed without a space so headings merged into domain names. Domains are now parsed per block line.
- vision: OCR crashed when Tesseract was not on PATH (common on Windows). It now returns no OCR draft and the author stage transcribes.
- Windows: the CLI re-runs itself in Python UTF-8 mode when the locale is not UTF-8, and child scripts get `PYTHONUTF8=1`, so UTF-8 official pages (en dashes in weight ranges) parse the same as on Linux.
- tests: the gold regression silently used a hardcoded `/workspace/certpassly` path and showed 8 skipped tests in CI. It now runs only with `CERTPASSLY_GOLD` and is not collected otherwise (0 skipped). New `tests/demo_kit.py`, `tests/test_demo_end_to_end.py` (both adapters, every stage through the CLI) and `tests/test_regressions_v102.py`.
- docs: SKILL_BODY.md had drifted from SKILL.md; a test now keeps them identical. SKILL.md documents the intake folder, the demo, and the remaining limits honestly.

## 1.0.1 (2026-11-11)

- Declare numpy, opencv-python-headless and Pillow as dependencies. The extract stage imports them; 1.0.0 wrongly said stdlib only, which failed on clean CI runners.
- Add GitHub Actions test workflow (Linux and Windows, Python 3.11 and 3.13).

## 1.0.0 (2026-11-11)

First packaged release of the CertPassly exam pipeline skill.

- Scripts-first pipeline (`run_pipeline.py` / `certpassly-pipeline`) with one marked AI stage (`author`).
- Versioned site-format snapshot under `reference/site-format/v1/` so the pipeline never reads the site app, artisan or GitHub.
- Vendor adapter pattern (`scripts/adapters/`) chosen from `config/vendors.yaml`, plus a generic official-source parser.
- Shared content blocks (`shared/`) with a configurable page-share cap (default 40 percent).
- Owner PDF extractor with layout detection and an unparsed-item report.
- Lesson gates in `validate.py` (official settings versus cover facts, skipped VCE files, vendor brand, sidecar meta, delivery partner, shared-section share and banned-term checks).
- Offline regression for a finished exam package (when a gold workspace is present) and a non-vendor-specific dry run that reports official-source gaps honestly.
- Git / pip / zip install: `SKILL.md` at repo root, `pyproject.toml` console entry point, `install.sh` and `install.ps1`.
