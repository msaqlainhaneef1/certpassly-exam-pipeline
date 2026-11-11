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
8. Flagged keys are never changed. Items with no answer in the owner file are never held or dropped: `answer_research` keys them only from saved OFFICIAL vendor pages (status unverified, reviewer needed) or flags them `answer_not_found` (draft, excluded from scoring).
9. Sheet versus Drive mismatches go to `review.csv`.
10. Pages stay draft. No Course schema on the practice-test page. Twitter / og:image / last-checked go in `page_meta_extras.csv`.
11. Batch AI. The only AI stage is `author`. Research uses a vendor adapter first; AI may fill only listed official gaps, each with a quote.
12. This pipeline never reads the site application, artisan or GitHub. It reads `reference/site-format/` (version from `site_format_version`, default `v1`).
13. All page prose and explanations follow [reference/writing-brief.md](reference/writing-brief.md): plain English, short sentences, people first, no banned AI phrases. Competitor notes are topics only. Never copy their wording.

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
| intake | no | Reads owner files from `owner-files/<CODE>/` (or `paths.owner_files` in `pipeline.yaml`), writes `intake/files.json` (sha256, use) and `rights-confirmation.md` from `owner_rights_statement`. PDFs are extracted; VCE and other binaries are skipped. Online, an empty owner folder is filled from the exam's public Drive folder link in `catalog.csv` (`drive_fetch.py`: subfolders, sha256 in `.fetch.json`, resume, clear errors for private/quota/HTML responses). Offline skips the download. |
| sources | no | With no hand-written research file, `research_init.py discover` finds the official pages from `catalog.csv` (vendor `seed_role` / `discover_sg` / `discover_cp` patterns), saves HTML + visible text + sha256. Plain fetch first; headless Chromium render (optional extra `[render]`) when the text is too short or the vendor sets `render: true`. Reuse saved copies. |
| research | parser first | `research_init.py build` writes `research/<vendor>/<CODE>.json` (plus vendor/cert files when missing) from the adapter output: every fact has source_id, url, sha256 and a verbatim quote, otherwise "not published by the vendor". Gaps go to `research/gaps.json` for one optional batched gap pass. Hand-written research files are never overwritten. |
| extract | no | Split the owner PDF (layout detected). Write `layout.json` and `unparsed.json`. |
| answer_research | pick only | No-answer items: candidate OFFICIAL pages (research sources, `authoring/answer_research_urls.json`, site-restricted search on `official_domains`), saved with sha256; matching lines ranked; region boxes proposed by script for image items. Non-official URLs are rejected and logged. |
| intent | no | `search_intent.py` writes `research/<vendor>/<CODE>.search-intent.json` from research facts only: the main query for each page, people-also-ask questions from official facts and recorded gaps, and which page answers each one. No number is invented. Topic labels from `research/<vendor>/<CODE>.competitor-notes.json` are recorded as topics only, each marked with whether a saved official page supports it. A person may edit the file (set `edited_by_person: true` to keep the edits). |
| author | YES | The AI stage. Batched: original page prose, rewritten explanations, `bank_meta`, visual transcription where OCR fails. Does not invent questions or change stems, options or keys. Also writes `answer_research.json` (key, source_url, verbatim quote, confidence) from `answer_research/candidates.json` in the same batch. `run_pipeline` only checks that the files exist. |
| pages | no | Build exam pages from research + `page_prose`. Insert shared sections by key. Render the five sourced tables (key facts, objectives, study plan, vendor exams, certification requirements) from research when the prose has none. Skip vendor/cert pages when unchanged. |
| writing | no | `check_writing.py` (no AI) applies the writing brief to the built pages and the explanations. Writes `writing-review.json` and `WRITING-REVIEW.md` (failed checks only) and `authoring/writing_fix_request.json` (only the flagged parts). Exit 1 on flags unless `writing.fail_on_flags` is false. Also runs after every pages rebuild. |
| import | no | Workbook CSVs, `page_meta_extras.csv`, simulator settings. |
| bank | no | `questions.json`, question CSVs, media, REVIEW.md, CLEANUP-LOG.md. No-answer items: researched key re-verified by script (official domain, saved copy, verbatim quote) and imported as `researched_unverified` / `key_source=researched_official` / `verification_status=unverified`; no evidence gives `answer_not_found`, listed in REVIEW.md and in `simulator_settings.json` `scoring_excluded_question_keys`. Intake-skipped files are listed in REVIEW.md automatically. |
| validate | no | Manifest, `validate.py`, `check_bank.py`. Exit 1 on a failed check. |
| package | no | Zip the exam package plus shared vendor and certification pages. |

## Writing brief, search intent and the check-then-fix loop

Read [reference/writing-brief.md](reference/writing-brief.md) before the author stage. It holds the plain-English rules, a short summary of Google's people-first guidance, the banned AI-phrase list with bad and good examples, and the self-check. The phrase list is data in `config/banned_ai_phrases.txt` (a workspace can add its own `config/banned_ai_phrases.txt`).

- Inputs for the author: the research file, the search-intent file `research/<vendor>/<CODE>.search-intent.json` (built by the `intent` stage), and the optional competitor-notes file `research/<vendor>/<CODE>.competitor-notes.json` from the CertPassly Researcher. Competitor notes are topics only. Cover a topic only when a saved official page supports it; otherwise skip it or say the vendor did not publish it.
- `build_pages.py` copies each page's main query and assigned questions into the page JSON (`search_intent`). It never reads competitor notes.
- The `writing` stage flags: banned AI phrases (vendor quotes found word for word on a saved official page are exempt), long sentences, typographic dashes, numbers that are not in the research files, thin pages, a high reading grade, search-intent questions a page does not answer (topic, official answer, source link), invented numbers in the search-intent file, and runs of 8 or more words copied from the competitor notes.
- Only the flagged parts go back for a fix (`authoring/writing_fix_request.json`). A part that had no flag and was rewritten in a fix round is flagged too. Then rerun `--stage pages --stage writing`. A second check is required: with `writing.validate_gate: true`, validate check 19 fails unless the latest writing check ran on the current files and found zero flags.
- Open flags stay in `REVIEW.md`. Never mark a record published or verified to clear a flag. The writing check never changes stems, options or keys.
- Settings live under `writing:` in `pipeline.yaml` (`fail_on_flags`, `validate_gate`, `max_sentence_words`, `competitor_overlap_words`, `min_words`, `max_grade`, `answer_window_chars`).

## Vendor adapters

`config/vendors.yaml` names the adapter for each vendor slug (`generic` or a module under `scripts/adapters/`). The generic adapter extracts duration, pass mark, question count, price, languages, delivery, prerequisites, renewal and domains/weights when they are clearly stated, and lists gaps otherwise. Do not add exam-specific branches in shared scripts.

## Shared sections

Reusable blocks under `shared/` (site, vendor, certification, question-type). Templates insert them by key. A block is written only if it does not already exist. A page may not take more than `shared_max_share` (default 40 percent) of its wording from shared blocks. See [reference/shared-sections.md](reference/shared-sections.md).

## Site-format

`reference/site-format/v1/` holds the 30 question types and aliases, CSV headers, simulator schema, page fields, slug/URL rules, allowed statuses, and sample import files. Bump or add a version folder; set `site_format_version` in `pipeline.yaml`. An artisan dry run is optional and only for someone who already has application access. It is not on the default path.

## Quality

`validate.py` and `check_bank.py` must pass. Lesson gates cover researched keys (official domain, saved sha256, verbatim quote, unverified flag: check 12l), answer_not_found items excluded from scoring and nothing held (12m), official versus cover facts, skipped VCE files, vendor brand, sidecar meta, owner-file provenance, delivery partner, shared-section share, and banned terms in shared blocks. Meta titles 50-60 characters; descriptions 140-160. Five sourced tables. JSON-LD: BreadcrumbList, credential, Course (study guide only), FAQPage (sourced answers only). No Review or Rating.

## Tests

`python -m unittest discover -s tests -v` (offline, no AI). CI runs it on Linux and Windows with 0 skipped tests.

- `tests/test_demo_end_to_end.py` builds two synthetic demo workspaces with `tests/demo_kit.py` (one per adapter path: the Microsoft adapter and the generic adapter) and runs every default stage through the CLI with no manual step. Each demo PDF carries seller branding, a social link, a phone, an email and a free-update line (stripping is checked), six items (single choice, multiple select, Yes/No matrix, inline drop-down, one image-only item with no evidence (answer_not_found), one no-answer item keyed by answer_research from a saved official page) and a skipped VCE file.
- `tests/test_v110.py`: answer_research (researched key + quote, answer_not_found, rejected non-official pick / non-verbatim quote / bad key), Drive download against a local mock (hash, resume, HTML error), render fallback, research JSON generation, and a grep gate for exam literals in scripts.
- `tests/test_v120.py`: writing brief file, banned-phrase checker (bad and good examples, vendor quotes), search intent from research facts only, intent coverage, competitor overlap, no model calls in the runner, and the full check-then-fix loop on a demo workspace (flags, fix request, unflagged change, second check, identical stems, options and keys).
- Try a demo yourself: `python tests/demo_kit.py microsoft DEMO_DIR` then `certpassly-pipeline --exam DM-101 --root DEMO_DIR --offline --date 2026-11-11` (generic path: profile `salesforce`, exam `Demo-Admn-101`).
- The gold-package regression on a real finished exam runs only when `CERTPASSLY_GOLD` points at a local gold workspace (real owner extracts are never committed). Without it, the regression is not collected, so it never shows as skipped.

## Limits

- The author stage is not a model call. Someone (or a separate batched job) must write the authoring files. The writing check flags problems; it does not rewrite text.
- Generic official-page parsing will miss facts that are not stated clearly. Those become gaps, not guesses.
- Owner PDFs with unusual layouts may leave items in `unparsed.json`.
- Drive download needs folders shared as "Anyone with the link". Private folders stop with a clear error.
- Rendering needs `pip install -e ".[render]"` and `python -m playwright install chromium`. Without it, JS-built pages stop with that instruction.
- `scripts/check_import_conformance.py` checks import files against `reference/site-format/v1`, including `key_source`, `verification_status`, `researched_unverified`, `answer_not_found` and `scoring_excluded_question_keys`. It does not run the live site importer.
- The site-restricted web search in answer_research may return nothing (search engines block scripts). Then only listed URLs and the exam's official sources are searched; the attempt is logged.
- Real-exam proof: Data-Con-101 has now run live through every default stage, including one batched author pass (65 short explanations and page prose), pages, import, bank, validate, check_bank and package. 65 imported, 0 held. Official facts (105 minutes, 70 percent, 60 questions, USD 200) come from the saved Salesforce exam guide.
- A non-editable `pip install .` is enough for `--help`. Full runs need a clone (`pip install -e .`) or `CERTPASSLY_SKILL_ROOT`.
- This skill does not publish pages, change site code, or write to the database.
