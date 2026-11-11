# AI operator guide

The complete manual for running and changing the CertPassly exam pipeline. It is written so that any AI agent (or person) can learn the skill from this repo alone and do every task without missing a step. Plain English. No typographic dashes.

How to use it:

1. Read sections 1 to 3 once. They are the rules. They never change mid-run unless the owner says so.
2. Do the exercises in [AI-TRAINING-EXERCISES.md](AI-TRAINING-EXERCISES.md) once.
3. For a real job, follow the runbook in section 9 and tick the checklist in section 12 before you report.

Contents:

1. What the skill is
2. Owner rules
3. Repo and workspace map
4. Setup
5. Stage order
6. Every stage in detail
7. The author pass
8. Validate gates
9. Runbooks
10. Troubleshooting
11. Changing the code and releasing
12. Before you say done
13. Report template

## 1. What the skill is

`certpassly-exam-pipeline` is a scripts-first pipeline. The command is `certpassly-pipeline` (entry point `scripts/run_pipeline.py`). For one exam it produces:

- Draft exam pages (exam hub, objectives, study guide, FAQ, practice test) plus shared vendor and certification pages, as JSON and HTML.
- A draft question bank (`questions.json`) and the site workbook CSVs under `out/<CODE>/import/`, plus `simulator_settings.json`.
- Review files (`REVIEW.md`, `CLEANUP-LOG.md`, `WRITING-REVIEW.md`), a validation report, and a zip package.

Inputs are official vendor pages (fetched, saved and hashed by script) and the owner's question PDF (usually from a shared Google Drive folder). The pipeline never reads the CertPassly site code, artisan, a database or the site GitHub repo. Site rules are a frozen snapshot in `reference/site-format/v1/`.

Everything is a script except one stage: `author`. The author pass is done by an AI (you) in one batched pass, by writing files. `run_pipeline.py` never calls a model. It checks the files and stops with instructions if they are missing.

## 2. Owner rules

These are the owner's rules. Re-read them and the workspace `config/pipeline.yaml` before each stage. If the owner gives a new rule mid-run, the new rule wins and you must say so in the report.

### 2.1 Brands and banned content

- Official vendor brands, product names, certification titles and exam codes are required on every page and must stay exactly as the vendor writes them (gate 17c). Do not rename a product to its newer name inside a question.
- CertPassly is the only site brand (gate 14). The brand and the disclaimer come from config, never from hand-written text.
- Never output a seller or competitor brand. Owner PDFs often carry the seller's brand on the cover, in headers and in a "seller note". Extract strips those lines. They must never reach any output, including the package zip.
- Never output social links, phone numbers, emails or free-update lines.
- The denylist is data: `brand_denylist` and `contact_patterns` in `config/pipeline.yaml` (template `config/pipeline.example.yaml`). Gates 14b, 18b and the package scan use it. Never print a denylist term in a user-facing doc or report; name the file and rule number instead.
- Keep a delivery partner that the vendor still names (for example Pearson VUE on Microsoft pages, gate 17f).

### 2.2 Questions and keys

- Questions come only from the owner PDF. Never invent a question, an option or a key.
- Exact question types are never merged. Types come from the registry in `reference/site-format/v1/question_types.json` and are assigned by `scripts/qtypes.py`. A DRAG DROP item is `drag_drop`, not a drop-down.
- Never change an owner key. When current official docs contradict it, keep the key and set the explanation accuracy to `key_wrong`, `key_outdated` or `key_arguable` with a note `n`. The keyed option's rationale says it is keyed in the owner file. The item is `flagged_for_owner`.
- Items with no answer in the owner file are never held and never dropped:
  - `answer_research` finds official pages. If the author pass picks a key with a verbatim quote from a saved official page, the item is `researched_unverified` (`key_source=researched_official`, `verification_status=unverified`, reviewer needed, gate 12l).
  - With no official evidence, the item is `answer_not_found`: a draft, listed in REVIEW.md and excluded from scoring in `simulator_settings.json` (gate 12m).
- Image-based items need a transcription (`extracted/visual_transcription.json`) and are marked `human_review_required`.
- VCE and other binary files are skipped by intake and listed in REVIEW.md (gate 17b). Never try to decrypt them.

### 2.3 Spelling, grammar and punctuation in stems and options

Stems and options get spelling, grammar and punctuation fixes only. Never change meaning, the correct answer, or option order. Official vendor product names stay exact. Every change is logged in `text-fixes.json` and gated by the key and option-order identity check (validate 12n).

- The `textfix` stage proposes fixes. Script rules (lost ligature, repeated word, space before punctuation, double space) apply on their own. Article (a or an) and possible typos wait for your decision in the author pass.
- Words on the saved official pages and every word with a capital letter are protected. A fix that drops one is rejected by the guard.
- The bank stage refuses to apply fixes if the key identity digest (key letters, option ids in order, option count, visual key) changes.

### 2.4 Facts

- Never trust cover-page facts in an owner file (duration, pass mark, question count). They are recorded as a conflict in `bank_meta.json` and the official value is used (gate 17).
- Every fact in research has `source_id`, `url`, `sha256` of the saved copy and a verbatim `quote` found on that page (gate 02). A value the vendor does not publish is `"value": null` with `"reason": "not published by the vendor"`, and pages say "not published by the vendor".
- Exam length never comes from the extra-time rule ("30 extra minutes"). Weights must sum to about 100 percent (gate 04).

### 2.5 Writing

- Plain English for grade 8 to 9 readers (gate 10 allows grade 11 or lower), short sentences (34 words or fewer), no em or en dashes anywhere (gate 08, writing check), no banned AI phrases (`config/banned_ai_phrases.txt`, gate 07 and the writing check).
- Pages answer the questions in `research/<vendor>/<CODE>.search-intent.json`. Numbers in prose must exist in the research files.
- Competitor notes are topics only. Never copy their wording (8 or more words in a row fails).
- Full rules: [../reference/writing-brief.md](../reference/writing-brief.md).

### 2.6 Pages, meta and schema

- Five fact tables are rendered from research, never typed by hand: key facts (exam hub), objectives, study plan, vendor exams, certification requirements (gate 11b). Key facts cells show a source link and checked date, or "not published by the vendor" (gate 11c).
- Titles 50 to 60 characters, meta descriptions 140 to 160, unique, one H1, an H2 outline, Open Graph and Twitter tags, canonical, `noindex` while draft, last updated date (gates 05 to 05j). Twitter, og:image and last-checked values also go in `page_meta_extras.csv` (gate 17d).
- JSON-LD: BreadcrumbList on every page (14d); EducationalOccupationalCredential on the certification page (14e); Course on the study guide only, never on the practice test (14f); FAQPage on the FAQ page with sourced answers only (14g). Organizations are only the brand (publisher) and the vendor (issuer) (14c).
- Never add Review or AggregateRating markup (14h).
- Pages and records stay draft. Never mark anything verified, reviewed, approved, published or active (gate 15).
- Shared blocks (`shared/`) may not exceed the configured share of a page body (default 40 percent, gate 18).

### 2.7 How we work

- Max scripts, min AI. `author` is the only AI stage. Research may use AI only for gaps the adapter lists, each with an official quote.
- Fix only the parts a check flagged, then rerun the check. A part that passed and was rewritten is flagged too.
- Never hardcode an exam code, vendor name, product name or count in shared scripts. Use config, `config/exam_lookup.json`, `config/catalog_overrides.json` and vendor adapters in `scripts/adapters/`. A test greps for exam literals.
- A bug found in a real run is fixed in the scripts with a test that uses synthetic data. Never commit real owner extracts.
- Proof only: every claim in a report carries commit SHAs, exit codes, counts and sha256 values.
- Only one run may write `out/<CODE>/` at a time. Parallelize across independent work, never two runs on one exam folder.
- Never print, store or commit a token. Never force-push. Never rewrite a tag.

## 3. Repo and workspace map

Skill repo (this repository):

- `AGENTS.md`: entry point for agents. `CLAUDE.md`, `.cursor/rules/certpassly.mdc` and `.github/copilot-instructions.md` point to it.
- `SKILL.md` and `SKILL_BODY.md`: the skill text. `SKILL_BODY.md` is `SKILL.md` without the front matter (a test checks this).
- `HANDOVER.md`: current state and open items. `CHANGELOG.md`: version history. `README.md`: install.
- `pyproject.toml`: package `certpassly-exam-pipeline`, entry point `certpassly-pipeline`, version.
- `install.sh`, `install.ps1`: installers for Linux or macOS and for Windows.
- `config/pipeline.example.yaml`: brand, disclaimer, denylist, contact patterns, banned phrases, writing settings, `package_exclude`, `text_fixes`, `owner_rights_statement`.
- `config/vendors.example.yaml`: vendor adapters and discovery patterns (`seed_role`, `discover_sg`, `discover_cp`, `render`).
- `config/exam_lookup.json`: known exam codes, vendor and official URLs. `config/catalog_overrides.json`: owner-sheet label rules.
- `config/banned_ai_phrases.txt`, `config/ligature_words.txt`: data for the writing check and the ligature tools.
- `scripts/run_pipeline.py`: the runner. Other scripts are named in section 6.
- `scripts/adapters/generic.py`, `scripts/adapters/microsoft.py`: official-page parsers.
- `reference/`: `lessons-learned.md`, `writing-brief.md`, `quality-gates.md`, `seo-and-schema.md`, `brand-rules.md`, `output-layout.md`, `shared-sections.md`, `troubleshooting.md`, and `site-format/v1/`.
- `schema/exam_research.schema.json`: research JSON schema.
- `shared/`: shared page blocks.
- `tests/`: the unit, gate and demo suites. `tests/demo_kit.py` builds synthetic demo workspaces.
- `.github/workflows/tests.yml`: CI on Ubuntu and Windows, Python 3.11 and 3.13.

Workspace (the `--root` folder, never inside the repo):

- `config/pipeline.yaml`, `config/vendors.yaml`: copied from the examples and edited.
- `sheet.csv`: the owner exam sheet. `catalog.csv`, `catalog.json`, `review.csv`: catalog output.
- `owner-files/<CODE>/`: owner PDF (and skipped VCE).
- `sources/<vendor>/`: saved official pages with `.json` sidecars (url, http, sha256, retrieved_at).
- `research/<vendor>/<CODE>.json`, `research/<vendor>/<CODE>.search-intent.json`, `research/<vendor>/<CODE>-bank-sources.json`, `research/vendors/<vendor>.json`, `research/certs/<cert>.json`, `research/gaps.json`.
- `out/<CODE>/`: everything for one exam (`intake/`, `extracted/`, `authoring/`, `pages/`, `import/`, `media/`, `questions.json`, `REVIEW.md`, `CLEANUP-LOG.md`, `text-fixes.json`, `writing-review.json`, `validation.json`). `out/vendors/`, `out/certifications/`: shared pages.
- `cache/linkcheck.json`: link-check cache for offline validate.
- `run.log`: the runner log. `<CODE>-package.zip` and `<CODE>-package.zip.scan.json`.

## 4. Setup

Requirements: Python 3.10 or newer (3.11 and 3.13 are tested), Git, Poppler (`pdftohtml`, `pdftoppm`) and Tesseract. Tesseract is optional; without it the author transcribes images.

Linux or macOS:

```
git clone https://github.com/msaqlainhaneef1/certpassly-exam-pipeline.git
cd certpassly-exam-pipeline
python -m venv .venv
source .venv/bin/activate
pip install -e .
certpassly-pipeline --help
certpassly-pipeline --list-stages
python -m unittest discover -s tests -v
```

Windows PowerShell:

```
git clone https://github.com/msaqlainhaneef1/certpassly-exam-pipeline.git
cd certpassly-exam-pipeline
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1
.\.venv\Scripts\Activate.ps1
certpassly-pipeline --list-stages
```

Optional JavaScript rendering for vendor pages that build their text in the browser:

```
pip install -e ".[render]"
python -m playwright install chromium
```

Make a workspace (replace the paths; `SKILL` is your clone):

```
SKILL=$PWD
WS=$HOME/certpassly-work
mkdir -p "$WS/config" "$WS/owner-files"
cp "$SKILL/config/pipeline.example.yaml" "$WS/config/pipeline.yaml"
cp "$SKILL/config/vendors.example.yaml" "$WS/config/vendors.yaml"
```

Then edit `$WS/config/pipeline.yaml`: set `owner_rights_statement` to the owner's statement about the files (one sentence, with the date). Leave the brand, disclaimer and denylist as they are unless the owner changes them.

Success: `certpassly-pipeline --list-stages` prints 15 stages and the test suite ends with `OK`.

## 5. Stage order

Stages always run in this order. `certpassly-pipeline --list-stages` prints the same table. With no `--stage` flag, every stage runs. A failed stage stops the run with a non-zero exit code.

1. `catalog`
2. `intake`
3. `sources`
4. `research`
5. `extract`
6. `textfix`
7. `answer_research`
8. `intent`
9. `author`
10. `pages`
11. `writing`
12. `import`
13. `bank`
14. `validate`
15. `package`

`textfix` runs right after `extract` (it only proposes); its fixes are applied in `bank`. `author` is the only AI stage; it also decides the `textfix` and `answer_research` proposals.

Common command shape (every example below uses it):

```
certpassly-pipeline --exam CODE --root "$WS" --date YYYY-MM-DD [--offline] [--stage NAME ...]
```

`--date` freezes the last-updated date (or set `CERTPASSLY_DATE`). Repeat `--exam` for more codes. `--vendor SLUG`, `--all` and `--batch` select exams from `catalog.csv`. `--sheet` points the catalog stage at the owner sheet. `--force` redoes extract. `--zip` sets the package path. `--config` points at a different `pipeline.yaml`.

## 6. Every stage in detail

Each stage below lists inputs, outputs, the exact command, what success looks like, and common failures with fixes. In every command, `CODE` is the exam code and `$WS` is the workspace. Every run appends to `$WS/run.log`. Read it after each stage.

When a run covers several exams, a failed stage stops that exam and the runner moves to the next one. The exit code is non-zero if any stage failed.

### Stage 1: `catalog`

- AI: no. Script: `scripts/build_catalog.py`.
- Inputs: the owner sheet CSV (`--sheet`, `paths.sheet` in config, or `$WS/sheet.csv`), `config/exam_lookup.json`, `config/catalog_overrides.json`.
- Outputs: `$WS/catalog.csv`, `$WS/catalog.json`, `$WS/review.csv` (rows that need the owner), saved official exam pages under `$WS/sources/`.
- Command: `certpassly-pipeline --root "$WS" --stage catalog --sheet "$WS/sheet.csv"`
- Success: `catalog.csv` has one row per exam with `vendor_slug`, `exam_code`, `drive_folder_url` and `official_exam_url` with `url_http` 200. Rows with an empty `official_exam_url` carry an `empty_reason`.
- Sheet format: a vendor header row, then one row per exam: label in column A, Drive folder link in column C. Example:

```
Microsoft,,
SC-900,,https://drive.google.com/drive/folders/FOLDER_ID
```

- Failures and fixes:
  - "no owner sheet and no catalog.csv. Pass --sheet FILE.": the owner gave only a Drive folder link. Build a one-row sheet like the example above (vendor row plus code row with the link), save it as `$WS/sheet.csv`, and say in the report that you built it.
  - Exam code not in `config/exam_lookup.json`: the row gets no official URL. Add the code with its vendor and official URL to `config/exam_lookup.json` (data, not code), then rerun.
  - A label that is not an exam: add a rule to `config/catalog_overrides.json`. Never special-case it in a script.

### Stage 2: `intake`

- AI: no. Scripts: `scripts/run_pipeline.py` with `scripts/drive_fetch.py`.
- Inputs: `catalog.csv` (Drive link), `owner_rights_statement` in `config/pipeline.yaml`, files in `$WS/owner-files/CODE/`.
- Outputs: `owner-files/CODE/` (downloaded PDF and other files, `.fetch.json` with sha256), `out/CODE/intake/files.json`, `out/CODE/intake/rights-confirmation.md`.
- Command: `certpassly-pipeline --exam CODE --root "$WS" --stage intake`
- Success: run.log shows `intake: wrote files.json from ... (N files; extracted, skipped: binary VCE, not decrypted)`. Each file has a sha256.
- Failures and fixes:
  - "set owner_rights_statement in pipeline.yaml": write the owner's rights statement into the workspace config, then rerun. Rights are the owner's call; never invent consent.
  - "intake: no PDF in ...": the folder has no PDF. Report it. A VCE alone cannot be used.
  - VCE skipped: this is correct. Record its sha256 in the report. REVIEW.md lists it (gate 17b).
  - Drive download fails: the folder must be shared as "anyone with the link". Ask the owner. Partial files end in `.part` and are redone on rerun.
  - intake is skipped as "already present": pass `--force` to rebuild it.

### Stage 3: `sources`

- AI: no. Scripts: `scripts/research_init.py` (discover) or `scripts/fetch_sources.py`.
- Inputs: `catalog.csv`, `config/vendors.yaml`, an existing research file if one was written by hand.
- Outputs: saved official pages in `sources/<vendor>/` with `.json` sidecars (url, http, sha256, retrieved_at), `research/<vendor>/CODE.sources.json`.
- Command: `certpassly-pipeline --exam CODE --root "$WS" --stage sources`
- Success: the study guide page and the certification page are saved with HTTP 200.
- Failures and fixes:
  - A page builds its text with JavaScript: install the `render` extra (section 4) and set `render` for the vendor in `config/vendors.yaml`.
  - Offline with missing sources: "sources missing in offline mode". Run once online, or copy the saved `sources/` folder from a previous workspace.
  - A non-official URL: only hosts on the vendor's official domains are accepted (gate 02c). Never add a third-party page as a source.

### Stage 4: `research`

- AI: parser first. Scripts: `scripts/research_init.py`, adapters in `scripts/adapters/`.
- Inputs: saved official pages, `config/vendors.yaml`, `schema/exam_research.schema.json`.
- Outputs: `research/<vendor>/CODE.json`, `research/<vendor>/CODE.parsed.json`, `research/vendors/<vendor>.json`, `research/certs/<cert>.json`, `research/gaps.json`.
- Command: `certpassly-pipeline --exam CODE --root "$WS" --stage research`
- Success: run.log shows `research CODE: N facts with quotes, M gaps, K domains`, and for adapters with a comparison, `agree` with `domains`, `passing_score` and `tasks` true.
- Gaps: `research/gaps.json` lists facts the pages did not state. In the gap pass you may fill a gap only with a verbatim quote from a saved official page, with its `source_id`, `url` and `sha256`. Otherwise keep `"value": null` and `"reason": "not published by the vendor"`.
- Failures and fixes:
  - "adapter disagrees with research JSON": a hand-written research file does not match the saved pages. Fix the research file to match the official page, or re-save the source. Never edit a saved source.
  - Unpublished facts: price, languages or question count are often not published. Leave them null with the reason. Pages then say "not published by the vendor". This is correct, not a failure.
  - A hand-written research file (no `generated_by` key) is never overwritten. Delete it only if the owner agrees.

### Stage 5: `extract`

- AI: no. Scripts: `scripts/extract_owner_pdf.py`, `scripts/analyze_visual.py`, `scripts/text_repair.py`.
- Inputs: the PDF listed in `out/CODE/intake/files.json`.
- Outputs: `out/CODE/extracted/split.json` (items with stem, options, key, marker), `extracted/raw.xml`, `extracted/cleanups.json`, `extracted/unparsed.json`, `extracted/visual_draft.json` and `media/src/`.
- Command: `certpassly-pipeline --exam CODE --root "$WS" --stage extract`
- Success: the item count matches the PDF, seller lines are removed (logged in `extracted/cleanups.json`, summarized later in `CLEANUP-LOG.md`), and visual items are listed in `visual_draft.json`.
- Failures and fixes:
  - Extract is skipped as "already present": pass `--force` after a script fix.
  - Lost ligatures (for example "unied" for "unified", "verication" for "verification"): the PDF font drops the fi, fl or ff glyph. `scripts/text_repair.py` repairs words it knows from `config/ligature_words.txt`. The `textfix` stage catches what is left. Never edit `split.json` by hand.
  - `pdftohtml` tops: some Poppler builds (seen on Windows Poppler 25.x) write many strings with the same `top` and `left`, or flipped tops, so a sort by position scrambles items. `page_tops_trustworthy()` in `scripts/extract_owner_pdf.py` detects this and keeps document order. If items still merge or split, add a synthetic test that reproduces the layout and fix the extractor.
  - A drag-and-drop item typed as a drop-down: the item has a DRAG DROP marker but its picture looks like blanks. Transcribe it as tiles and targets (section 7.4). Gate 12f fails until you do.
  - Raw extracts contain seller lines on purpose (audit). They never ship. See stage 15.

### Stage 6: `textfix`

- AI: decide only. Script: `scripts/text_fixes.py`.
- Inputs: `extracted/split.json`, saved official pages (protected words), `text_fixes` in `config/pipeline.yaml`.
- Outputs: `out/CODE/text-fixes-proposals.json` (proposals with ids, kinds, before and after, and an `undecided` list).
- Command: `certpassly-pipeline --exam CODE --root "$WS" --stage textfix`
- Success: `textfix: N proposals {kind: count}; M need an author decision`.
- Kinds: `lost_ligature`, `repeated_word`, `space_before_punct` and `double_space` are applied on their own. Articles and possible typos are undecided until you decide them in `authoring/text_fixes_decisions.json` (section 7.6).
- Failures and fixes:
  - The author stage lists `text_fixes_decisions.json (accept or reject N proposals ...)`: decide every undecided id.
  - A fix that would change a capitalized or protected word is rejected later by the bank guard. Do not try to force it.

### Stage 7: `answer_research`

- AI: pick only. Script: `scripts/answer_research.py`.
- Inputs: items with no key in `split.json`, held image items, research sources, `authoring/answer_research_urls.json` (optional, URLs per item), online search over the vendor's official domains.
- Outputs: `out/CODE/answer_research/candidates.json` (saved pages and ranked quote lines per item), `answer_research/result.json` (status per item).
- Command: `certpassly-pipeline --exam CODE --root "$WS" --stage answer_research`
- Success: either "every item has an answer in the owner file; nothing to research", or a count by status (`pending_ai_pick`, `researched_official`, `answer_not_found`).
- Failures and fixes:
  - Non-official URLs are rejected and logged. That is correct.
  - Offline: only saved pages are used. Items with no evidence become `answer_not_found`.

### Stage 8: `intent`

- AI: no. Script: `scripts/search_intent.py`.
- Inputs: research facts, gaps, optional `research/<vendor>/CODE.competitor-notes.json` (topics only).
- Outputs: `research/<vendor>/CODE.search-intent.json`: the main query per page, people-also-ask questions, and which page answers each.
- Command: `certpassly-pipeline --exam CODE --root "$WS" --stage intent`
- Success: the file exists and every question points to one page. A person may edit it.

### Stage 9: `author`

- AI: YES. This is the only AI stage. Script: `scripts/run_pipeline.py` checks files only.
- Inputs: everything above, plus `reference/writing-brief.md`.
- Outputs (written by you): `out/CODE/authoring/explanations_text.json`, `explanations_visual.json`, `page_prose.json`, `bank_meta.json`, `answer_research.json` (when items are pending), `text_fixes_decisions.json` (when proposals are undecided), and `out/CODE/extracted/visual_transcription.json` (when there are visual items).
- Command: `certpassly-pipeline --exam CODE --root "$WS" --stage author`
- Success: `author: required files present (explanations, page_prose, bank_meta). AI is not invoked by this script.`
- Failure: `AUTHOR STAGE (the only AI stage). Files still needed:` followed by the missing files. Write them in one batched pass (section 7) and rerun.

### Stage 10: `pages`

- AI: no. Scripts: `scripts/build_pages.py`, `scripts/render_page.py`, `scripts/shared_sections.py`.
- Inputs: research, `authoring/page_prose.json`, `shared/`, search intent.
- Outputs: `out/CODE/pages/*.json` and `*.html`, `out/vendors/<vendor>/`, `out/certifications/<cert>/`.
- Command: `certpassly-pipeline --exam CODE --root "$WS" --stage pages`
- Success: seven pages built. When `writing` is not also selected, the runner runs the writing check in record mode right after.
- Failures and fixes: a missing shared block is reported as "shared blocks not on disk yet". Write it under `shared/` or remove the key.

### Stage 11: `writing`

- AI: no. Script: `scripts/check_writing.py`.
- Inputs: built pages, author files, research, search intent, competitor notes.
- Outputs: `out/CODE/writing-review.json`, `out/CODE/WRITING-REVIEW.md` (failed checks only), `out/CODE/writing-self-check.json`, and `authoring/writing_fix_request.json` when there are flags.
- Command: `certpassly-pipeline --exam CODE --root "$WS" --stage pages --stage writing`
- Success: `writing CODE: round N, 0 flags`.
- Flags: `banned_ai_phrase`, `long_sentence`, `typographic_dash`, `unsourced_number`, `thin_page`, `reading_grade`, `search_intent_missed`, `search_intent_number`, `competitor_copy`, `unflagged_part_changed`.
- Fix loop: open `authoring/writing_fix_request.json`, fix only the listed parts (for example `page_prose:exam_hub`), then rerun `--stage pages --stage writing`. The round number goes up. Rewriting a part that was not flagged is itself a flag.

### Stage 12: `import`

- AI: no. Script: `scripts/emit_import.py`.
- Inputs: research, pages.
- Outputs: `out/CODE/import/*.csv` (the site workbook, including `page_meta_extras.csv`) and `out/CODE/import/MANIFEST.json`.
- Command: `certpassly-pipeline --exam CODE --root "$WS" --stage import`
- Success: CSVs written; import key columns filled (gate 01b).

### Stage 13: `bank`

- AI: no. Scripts: `scripts/build_bank.py`, `scripts/text_fixes.py`, `scripts/qtypes.py`.
- Inputs: `split.json`, `visual_transcription.json`, every author file, `answer_research/result.json`, text fix proposals and decisions.
- Outputs: `out/CODE/questions.json`, `out/CODE/simulator_settings.json`, `out/CODE/text-fixes.json`, `out/CODE/REVIEW.md`, `out/CODE/CLEANUP-LOG.md`, and the question rows of the import CSVs.
- Command: `certpassly-pipeline --exam CODE --root "$WS" --stage bank`
- Success: `imported N held 0 researched R answer_not_found A flagged F {type counts}`.
- Failures and fixes:
  - "author stage: no explanation for qNNN": add the item to `explanations_text.json` or `explanations_visual.json`.
  - "text_fixes: author fixes rejected by the guard": your `extra` fix changed a protected word, the meaning or the key. Remove it or keep only the spelling part.
  - Key identity changed: the bank refuses to apply fixes. Find the fix that touched a key or the option order and drop it.

### Stage 14: `validate`

- AI: no. Scripts: `scripts/manifest.py`, `scripts/gen_site_question_types.py`, `scripts/validate.py`, `scripts/check_bank.py`.
- Inputs: everything in `out/CODE/`, research, saved sources, `cache/linkcheck.json` (offline).
- Outputs: `out/CODE/validation.json`, `out/CODE/SITE-QUESTION-TYPES.md`, manifest hashes, a check_bank summary.
- Command: `certpassly-pipeline --exam CODE --root "$WS" --stage validate`
- Success: every check line starts with `ok` (64 checks; count them with the command in section 8) and check_bank prints `Summary: N passed, 0 failed, N total`. Then run the conformance check: `python scripts/check_import_conformance.py --root "$WS" --exam CODE` (exit 0).
- validate refreshes the manifest. It does not rebuild the bank; after any author change, run `bank` (and `pages`, `writing`, `import`) first.
- Failures: see section 8 and section 10.

### Stage 15: `package`

- AI: no. Scripts: `scripts/run_pipeline.py` with `scripts/package_guard.py`.
- Inputs: `out/CODE/`, `out/vendors/<vendor>/`, `out/certifications/<cert>/`, `run.log`, `package_exclude` in config.
- Outputs: `$WS/CODE-package.zip` (or `--zip PATH`) and `CODE-package.zip.scan.json`.
- Command: `certpassly-pipeline --exam CODE --root "$WS" --stage package`
- Success: `package scan: M members, T text files scanned, I images skipped, 0 nested archives, 0 denylist hits` and `package written: ...`. Report the zip size and sha256.
- What is excluded: everything in `package_exclude` (raw extracts such as `extracted/raw.xml`, `extracted/*.txt`, `extracted/cleanups.json`, `extracted/unparsed.json`, `extracted/visual_draft.json`, `media/src/*`). Any other file under `extracted/` that still holds a removed seller line is dropped too. A redacted cleanups log (counts, reasons, sha256 and lengths, no removed text) and `PACKAGE-EXCLUDED.json` ship instead. The workspace copies stay for audit.
- Failure: `DENYLIST HIT <file>: denylist term #N`, then `package removed: it must not ship with denylist hits`. The zip is deleted. Find the file, remove the term at its source (usually an author file or a raw extract that should be excluded), rerun from the stage that writes that file, then rerun `package`. Never weaken the denylist to pass.

## 7. The author pass

The author pass is the only AI work. Do it in one batched pass per exam: write every file below, then run the remaining stages. Read `reference/writing-brief.md`, `research/<vendor>/CODE.search-intent.json`, `research/<vendor>/CODE.json`, `out/CODE/extracted/split.json` and `out/CODE/extracted/visual_draft.json` first. All files are UTF-8 JSON in `out/CODE/authoring/` unless noted. The synthetic demo (`python tests/demo_kit.py microsoft DIR`) writes a complete, passing example of every file. Copy its shape, never its text.

Limits for every text you write: grade 8 to 9, sentences of 34 words or fewer, no em or en dashes, no banned AI phrases, no numbers that are not in research, no seller or competitor names, no contact lines.

### 7.1 `explanations_text.json` (text items)

One entry per text item (`single_choice`, `multiple_select` and other option types), keyed by item id:

```
{"q001": {"c": "A secret store keeps keys and passwords out of app code.",
          "o": ["Right. It holds secrets.", "Wrong. Reports do not store secrets.",
                "Wrong. Themes change look only.", "Wrong. Layouts arrange fields."],
          "s": ["SG"],
          "a": "key_matches_current_docs"}}
```

- `c`: the core explanation, one or two sentences, original words.
- `o`: one rationale per option, in option order, same count as the options. Start with "Right." or "Wrong.".
- `s`: source ids from research (for example `SG` for the study guide).
- `a`: accuracy, one of `key_matches_current_docs`, `key_could_not_be_checked`, `key_wrong`, `key_outdated`, `key_arguable` (the last three flag the item for the owner), and `key_researched_official` for researched keys.
- `n`: required when `a` is `key_wrong`, `key_outdated` or `key_arguable`. Say what the current docs say. The keyed option's rationale says it is keyed in the owner file.

### 7.2 `explanations_visual.json` (visual items)

Same fields, but `o` follows the item shape:

- `yes_no_matrix`: one rationale per row: `"o": ["Yes. Group scope is supported.", "No. Default retention is shorter."]`.
- `inline_dropdown`: one list per blank, one rationale per choice: `"o": [["Right. Daily is the stated schedule.", "Wrong. Weekly is too sparse here.", "Wrong. Monthly is too sparse here."]]`.
- `drag_drop`: one list per target, one rationale per tile: `"o": [["Right. ...", "Wrong. ...", "Wrong. ..."]]`.

### 7.3 `page_prose.json` (page copy)

Top-level keys: `exam_code` plus one object per page: `exam_hub`, `objectives`, `study_guide`, `faq`, `practice_test`, `vendor`, `certification`. Each page object has:

- `title_candidates`: list of titles, each 50 to 60 characters, unique across pages, ending with the brand.
- `desc_candidates`: list of meta descriptions, each 140 to 160 characters.
- `h1`: one H1.
- `body_html`: the body. Use `<h2>` headings, `<p>`, `<ul>`. It must answer every question the search-intent file assigns to the page and include the required H2 topics for gate 11:
  - `exam_hub`: key facts, what the exam covers, what changed.
  - `objectives`: weights at a glance.
  - `study_guide`: study plan by skill area, before exam day.
  - `faq`: how long, pass, cost, languages.
  - `practice_test`: not ready, free official practice.
  - `vendor`: exams on (the vendor).
  - `certification`: requirements.
- Shared blocks go in `body_html` as tokens: `{{shared:site:editorial-policy}}`, `{{shared:site:simulator-how-it-works}}`, `{{shared:site:exam-day-checklist}}`, `{{shared:vendor:microsoft:booking}}` (files under `shared/site/` and `shared/vendor/<vendor>/`). List them in `shared_keys` as objects: `[{"level": "site", "key": "editorial-policy"}]`. Shared text may not exceed 40 percent of a page body.
- Fact tables are rendered by script. Never type facts into a table in `body_html`. `vendor` and `certification` carry `"tables": {"exams": []}` and `"tables": {"requirements": []}`.
- Extra fields: `study_guide.course_description` (Course schema text), `faq.faq_sourced` (list of H2 questions whose answers come from an official source; only these go into FAQPage schema) and `faq.faq_unsourced` (the rest), `certification.crumb_name` (short breadcrumb name), optional `exam_hub.price_note`.

### 7.4 `extracted/visual_transcription.json` (visual items)

Lives in `out/CODE/extracted/`. One entry per visual item, transcribed exactly from the image:

- `yes_no_matrix`: `{"rows": ["statement 1", "statement 2"], "key": ["yes", "no"]}`.
- `inline_dropdown`: `{"blanks": [["daily", "weekly", "monthly"]], "labels": ["Backups run"], "template": "Backups run {{blank1}}.", "key": [0]}`.
- `drag_drop`: `{"tiles": ["daily", "weekly", "monthly"], "targets": ["Backups run"], "key": [0]}` (key gives the tile index for each target).
- An item whose image shows no key: `{"held": true, "reason": "...", "candidate_regions": []}`. answer_research then takes over.

Use the type the source marker says (gate 12f). Image text must match exactly (gate 12g).

### 7.5 `bank_meta.json`

```
{"skill_rules": [{"pattern": "sign-in|secret|roles", "topic": "1.1"}],
 "default_topic": "2.1",
 "off_syllabus": {},
 "exhibit_alts": {},
 "cover_facts_conflict": ["Cover says 800 / 120 (pass mark / minutes). Official page: 700 or greater / 100 minutes."],
 "skipped_files": []}
```

- `skill_rules`: regex patterns that map an item to an official skill area id. `default_topic` for the rest.
- `off_syllabus`: optional `{"pattern": "...", "when_topic": "...", "flag": "possibly off-syllabus"}`.
- `exhibit_alts`: alt text for exhibit images, by item id.
- `cover_facts_conflict`: every cover-page fact that differs from the official value.
- `skipped_files`: names of skipped files (the VCE) if you want them named beyond intake.

### 7.6 `text_fixes_decisions.json`

```
{"decisions": {"q012:stem:article:30": {"accept": true, "note": "an before a vowel sound"},
               "q040:option.b:typo:4": {"accept": true, "after": "configuration", "note": "spelling"},
               "q051:stem:typo:18": {"accept": false, "note": "product name, keep as is"}},
 "extra": [{"item": "q042", "field": "stem", "before": "teh policy", "after": "the policy",
            "kind": "spelling", "reason": "spelling"}]}
```

- Decide every id in the `undecided` list of `out/CODE/text-fixes-proposals.json`. Ids look like `item:field:kind:offset` (for example `q001:stem:lost_ligature:51`). `after` may replace the proposed text.
- `extra` adds fixes the script missed. `field` is `stem` or `option.<id>` (for example `option.a`). `before` is exact text from the item. `kind` is `spelling`, `grammar` or `punctuation`.
- The guard rejects any fix that changes a protected or capitalized word, the key or the option order.

### 7.7 `answer_research.json` and `answer_research_urls.json`

For each item with status `pending_ai_pick` in `answer_research/result.json`, pick from `answer_research/candidates.json`:

```
{"q006": {"key": ["a"],
          "source_url": "https://learn.microsoft.com/en-us/training/docs/demo-data-export",
          "quote": "The Data export service exports data on a schedule, weekly or monthly.",
          "confidence": "high",
          "explanation": {"c": "...", "o": ["...", "...", "..."], "a": "key_researched_official", "s": []}},
 "q005": {"answer_not_found": true, "note": "No official page describes this screen."}}
```

- The quote must appear word for word in the saved official page. The script checks it.
- No evidence means `answer_not_found`. Never guess.
- `answer_research_urls.json` (optional) lists more official URLs per item: `{"q006": ["https://..."]}`. Non-official hosts are rejected.

### 7.8 `writing_fix_request.json` (input to a fix round)

Written by the writing stage. It lists the flagged parts only, for example `page_prose:exam_hub`. Fix those parts, leave every other part byte for byte the same, and rerun `--stage pages --stage writing`.

### 7.9 Author self-check

Tick every line before you run the remaining stages:

- Every item in `split.json` has an explanation (text or visual) with one rationale per option, row, choice or tile.
- No key was changed. Every contradicted key is flagged with `a` and `n`.
- Every visual item has a transcription with the type its marker says, copied exactly.
- Every `pending_ai_pick` has a verbatim official quote or `answer_not_found`.
- Every undecided text fix is decided. No fix touches meaning, keys, order or product names.
- Every page answers its search-intent questions and has the required H2 topics.
- Titles 50 to 60 characters, descriptions 140 to 160, all unique.
- No em or en dashes, no banned phrases, no seller, competitor, social, phone, email or free-update text, no numbers that are not in research.
- Official product names exact. CertPassly is the only site brand.
- Nothing is marked verified, reviewed, approved, published or active.

## 8. Validate gates

`scripts/validate.py` runs 64 checks: 01, 01b, 01c, 02, 02b, 02c, 03, 03b, 04, 05 to 05j, 06, 06b, 07, 09, 08, 09b, 09c, 10, 11, 11b, 11c, 12, 12e, 12f, 12g, 12h, 12i, 12k, 12j, 12l, 12n, 12m, 12b, 12c, 12d, 13, 14, 14b to 14h, 15, 16, 17, 17b to 17f, 18, 18b, 19. The full list with reasons is in `reference/quality-gates.md`. Count the results:

```
python -c "import json,sys; d=json.load(open(sys.argv[1])); print('ok', sum(c['passed'] for c in d), 'fail', sum(not c['passed'] for c in d))" "$WS/out/CODE/validation.json"
```

Success is `ok 64 fail 0`. Then check_bank must print `0 failed`.

Run validate through the runner. If you call `scripts/validate.py` directly, set `CERTPASSLY_ROOT` to the workspace and `PYTHONUTF8=1`, or it reads the wrong folder and crashes:

```
CERTPASSLY_ROOT="$WS" PYTHONUTF8=1 python scripts/validate.py "$WS/research/microsoft/CODE.json" --offline
```

## 9. Runbooks

### 9.1 New exam from a Drive link, end to end

1. Set up the skill and a workspace (section 4). Set `owner_rights_statement`.
2. If the owner gave a sheet, save it as `$WS/sheet.csv`. If they gave only a Drive folder link, build a one-row sheet (stage 1) and say so in the report.
3. Check the exam code is in `config/exam_lookup.json`. If not, add it (code, vendor, official URL) as data.
4. Run the script stages up to the author pass:

```
certpassly-pipeline --root "$WS" --stage catalog --sheet "$WS/sheet.csv"
certpassly-pipeline --exam CODE --root "$WS" --date YYYY-MM-DD --stage intake --stage sources --stage research --stage extract --stage textfix --stage answer_research --stage intent --stage author
```

5. The author stage exits non-zero and lists the files it needs. Do the author pass (section 7) in one batch.
6. Run the rest:

```
certpassly-pipeline --exam CODE --root "$WS" --date YYYY-MM-DD --stage author --stage pages --stage writing --stage import --stage bank --stage validate --stage package
```

7. If writing flags parts, fix only those parts and rerun `--stage pages --stage writing`, then `--stage import --stage bank --stage validate --stage package`.
8. Run the conformance check and record the proof (section 13):

```
python scripts/check_import_conformance.py --root "$WS" --exam CODE
sha256sum "$WS/CODE-package.zip"
```

### 9.2 Vendor batch

```
certpassly-pipeline --root "$WS" --stage catalog --sheet "$WS/sheet.csv"
certpassly-pipeline --root "$WS" --vendor microsoft --batch --date YYYY-MM-DD
```

- Runs every catalog exam for the vendor in sheet order. Each exam stops at `author` until its files exist; do one author batch per exam, then rerun the same command.
- A failed exam does not stop the next one. Read `failed=[...]` at the end of `run.log`.
- Never start a second run on an exam that is already running. One run per exam folder.

### 9.3 Offline

```
certpassly-pipeline --exam CODE --root "$WS" --date YYYY-MM-DD --offline
```

- Needs saved sources in `sources/<vendor>/`, owner files in `owner-files/CODE/`, and `cache/linkcheck.json` with every external link (gate 09c). Run once online first to fill the cache.
- No Drive download and no web search. Items with no saved evidence become `answer_not_found`.

### 9.4 Rerun after a change

- Author file changed: rerun `pages`, `writing`, `import`, `bank`, `validate`, `package`.
- Script fixed in extract: rerun with `--force` from `extract`.
- Research changed: rerun from `research`.

## 10. Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| Words like "unied", "verication", "oce" | Lost fi, fl or ff ligatures in the PDF font | `scripts/text_repair.py` and the `textfix` stage fix them; add a word to `config/ligature_words.txt` if needed; check `text-fixes.json` |
| FAIL 12f, "DRAG DROP marker but type is inline_dropdown" | Visual item transcribed as blanks | Transcribe as `tiles`, `targets`, `key` and give `o` per target per tile |
| Page says "not published by the vendor" | Official page does not state the fact | Correct. Keep null with the reason; fill only from a verbatim official quote in the gap pass |
| FAIL 11 with missing H2 topics | Page lacks a required heading topic | Add the H2 topic listed in section 7.3 to that page only |
| `DENYLIST HIT ... denylist term #N` at package | A seller or banned term in a shipped file | Remove it at the source file, rerun the stage that writes it, rerun `package` |
| Two runs on one exam folder, files half written | Concurrent runs | Stop one (`ps aux` and look for `certpassly-pipeline` with the same `--exam`), then rerun the stages from the earliest one the other run touched |
| "no owner sheet and no catalog.csv" | Owner gave only a Drive link | Build a one-row `sheet.csv` (stage 1) |
| VCE listed as skipped | Binary file, never decrypted | Correct. Report its sha256 |
| `UnicodeDecodeError` or garbled text on Windows | Legacy code page | Use `certpassly-pipeline` (it re-runs itself in UTF-8 mode) or set `PYTHONUTF8=1` before a direct script call |
| FAIL 09c "offline; cached 0; missing [...]" | No link-check cache offline | Run validate once online, or restore `cache/linkcheck.json` |
| Items merged or out of order on Windows | Poppler wrote untrustworthy `top` values | `page_tops_trustworthy()` keeps document order; add a synthetic test if a new layout breaks |
| "text_fixes: author fixes rejected by the guard" | A fix changed a protected word | Drop or narrow the fix |
| FAIL 12n | Keys or option order changed after a fix | Find the fix that touched them and remove it, rerun `bank` |
| FAIL 19 | Writing check not rerun after a change | Rerun `--stage pages --stage writing` |

More: `reference/troubleshooting.md` and `reference/lessons-learned.md`.

## 11. Changing the code and releasing

### 11.1 Rules for code changes

- Fix bugs in scripts, never by hand-editing outputs. Add a test with synthetic data in `tests/` (see `tests/demo_kit.py` and `tests/fixtures/README.md`). Never commit real owner text, extracts or packages.
- No hardcoded exam codes, vendor names or counts in `scripts/` (a test scans for them). Put data in `config/` or an adapter in `scripts/adapters/`.
- Keep Python 3.10 compatible syntax (no backslashes inside f-string expressions). Open files with `encoding='utf-8'`. Use `os.path.join`, never hard-coded slashes in paths.
- `SKILL_BODY.md` must equal `SKILL.md` without its front matter. After editing `SKILL.md`, regenerate it:

```
python -c "s=open('SKILL.md',encoding='utf-8').read(); open('SKILL_BODY.md','w',encoding='utf-8').write(s.split('\n---\n',1)[1].lstrip('\n'))"
```

- New docs: no em or en dashes, no denylist terms (`tests/test_ai_guide.py` checks this guide, the exercises, `AGENTS.md` and `HANDOVER.md`).
- Bump `version` in `pyproject.toml` and add a dated `CHANGELOG.md` entry for every release.

### 11.2 Tests

Run the full suite on Python 3.11 and 3.13 before every commit:

```
cd tests && python -W ignore -m unittest discover -s . -p 'test_*.py'
```

From the repo root, `python -m unittest discover -s tests -v` does the same (this is what CI runs). Success ends with `OK`. Report the count (`Ran N tests`) and the exit code for each Python version.

### 11.3 Release and push flow

1. Branch from main: `git checkout main && git pull --ff-only && git checkout -b TYPE/NAME`.
2. Change, test on 3.11 and 3.13, commit with a clear message.
3. Push the branch. Authenticate with a one-off header from the `GITHUB_TOKEN` environment variable. Never print the token, never write it into git config, a remote URL or a file:

```
AUTH=$(printf 'x-access-token:%s' "$GITHUB_TOKEN" | base64 -w0)
git -c http.extraHeader="Authorization: Basic $AUTH" push origin TYPE/NAME
```

4. CI (`.github/workflows/tests.yml`) runs on push to main, on pull requests and on `workflow_dispatch`. For a branch, start it by hand:

```
curl -s -X POST -H "Authorization: Bearer $GITHUB_TOKEN" -H "Accept: application/vnd.github+json" https://api.github.com/repos/msaqlainhaneef1/certpassly-exam-pipeline/actions/workflows/tests.yml/dispatches -d '{"ref":"TYPE/NAME"}'
```

5. Wait until all 4 jobs (ubuntu-latest and windows-latest, Python 3.11 and 3.13) are `success`. List runs with `GET /repos/msaqlainhaneef1/certpassly-exam-pipeline/actions/runs?branch=TYPE/NAME` and jobs with `GET /repos/msaqlainhaneef1/certpassly-exam-pipeline/actions/runs/RUN_ID/jobs`.
6. Merge fast-forward only: `git checkout main && git merge --ff-only TYPE/NAME`.
7. Tag with an annotated tag: `git tag -a vX.Y.Z -m "vX.Y.Z: summary"`.
8. Push main and the tag, never with force:

```
git -c http.extraHeader="Authorization: Basic $AUTH" push origin main
git -c http.extraHeader="Authorization: Basic $AUTH" push origin vX.Y.Z
```

9. Confirm the main push CI run is green (4 jobs). Report the commit SHA, the tag object SHA (`git rev-parse vX.Y.Z`) and the commit it points to (`git rev-parse vX.Y.Z^{commit}`).

Never force-push, never move or delete a pushed tag, never push to main without the owner asking. If a fast-forward is not possible, stop and report.

## 12. Before you say done

Tick every line. If one fails, you are not done.

- [ ] Every stage you ran exited 0, or you report the exact failure and why.
- [ ] `validation.json` gives `ok 64 fail 0`; check_bank gives `0 failed`; the conformance check exits 0.
- [ ] Writing check: last round has 0 flags (gate 19).
- [ ] Bank: imported count equals items in `split.json`; `held 0`; researched and answer_not_found items are listed in REVIEW.md.
- [ ] Every flagged owner key is listed with its reason.
- [ ] Text fixes: counts by kind and the key identity sha256 from `text-fixes.json` (identical before and after).
- [ ] Package: scan shows 0 denylist hits; you have the zip size and sha256.
- [ ] VCE and other skipped files are named with sha256.
- [ ] No seller, competitor, social, phone, email or free-update text anywhere you wrote, including the report.
- [ ] No em or en dashes and no banned phrases in anything you wrote.
- [ ] Code changes: tests added, suite green on 3.11 and 3.13, no hardcoded exam or vendor, `SKILL_BODY.md` identical.
- [ ] Release: branch CI green (4 jobs), ff-only merge, annotated tag, main CI green, no force-push.
- [ ] No token was printed or stored.
- [ ] Every claim in the report has proof (SHAs, exit codes, counts, sha256).

## 13. Report template

Copy this and fill every field. Write "n/a" with a reason for a field that does not apply. Never leave a field out.

```
Result: <one line: done, or blocked and why>

Run
- Exam(s): <CODE ...>  Vendor: <slug>  Workspace: <path>  Date flag: <YYYY-MM-DD>
- Skill version: <pyproject version>  Commit: <git rev-parse HEAD>
- Owner inputs: PDF <name> sha256 <...>; skipped <name> sha256 <...> (<reason>); sheet <given | built one row>
- Stages and exit codes: catalog <n> intake <n> sources <n> research <n> extract <n> textfix <n> answer_research <n> intent <n> author <n> pages <n> writing <n> import <n> bank <n> validate <n> package <n>

Bank
- imported <n> held <n> researched <n> answer_not_found <n> flagged <n>
- Types: <type: count, ...>
- Flagged owner keys: <qkey reason, ...>
- Text fixes: <n> {kind: count}; key identity sha256 <...> identical <true|false>

Gates
- validate: ok <n> fail <n> (failed ids: <...>)
- check_bank: <n> passed, <n> failed
- conformance: exit <n>
- writing: round <n>, <n> flags

Package
- <path> size <bytes> sha256 <...>
- scan: <members> members, <text> text files, <images> images skipped, <hits> denylist hits

Code and release (if any)
- Commits: <sha subject, ...>
- Tests: 3.11 Ran <n> exit <n>; 3.13 Ran <n> exit <n>
- CI: branch run <id> jobs <4 x result>; main run <id> jobs <4 x result>
- Tag: <vX.Y.Z> object <sha> -> commit <sha>

Open items and owner decisions needed
- <...>
```
