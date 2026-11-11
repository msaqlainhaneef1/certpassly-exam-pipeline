# HANDOVER.md

Current state of the CertPassly exam pipeline skill, for the next person or AI agent. Plain English. No typographic dashes.

Start with [AGENTS.md](AGENTS.md). The full manual is [docs/AI-OPERATOR-GUIDE.md](docs/AI-OPERATOR-GUIDE.md) and the self-training path is [docs/AI-TRAINING-EXERCISES.md](docs/AI-TRAINING-EXERCISES.md). This file records where the project stands, what was proven, and what is still open.

## 1. What the skill is

A scripts-first pipeline named `certpassly-exam-pipeline` (command `certpassly-pipeline`). It builds draft CertPassly exam pages and question import files from official vendor pages and the owner's question PDFs. It never talks to the site app, artisan, a database or the site GitHub repo. Site rules are a snapshot under `reference/site-format/v1/`.

Stage order (from `certpassly-pipeline --list-stages`): `catalog`, `intake`, `sources`, `research`, `extract`, `textfix`, `answer_research`, `intent`, `author`, `pages`, `writing`, `import`, `bank`, `validate`, `package`. Only `author` is an AI stage. Every stage is explained in the operator guide, section 6.

## 2. Versions

- v1.0.0 to v1.0.2: first pipeline, generic parsing, tables from research.
- v1.1.0: answer research (`researched_unverified`, `answer_not_found`), JavaScript rendering, AB-730 q089.
- v1.1.1 to v1.1.3: CI fixes for Python 3.11 f-strings and POSIX paths.
- v1.1.4: Data-Con-101 from author through package.
- v1.1.5: Windows install from GitHub, Poppler `top` fallback.
- v1.2.0: writing brief, banned AI phrases as data, search intent, competitor notes as topics only, writing check and fix loop (gate 19), DRAG DROP as `drag_drop`, lost-ligature repair, package guard (no raw extracts, zip denylist scan), spelling, grammar and punctuation fixes for stems and options with the key identity gate (12n).
- v1.2.1: documentation only. `AGENTS.md`, the AI operator guide, the training exercises, pointer files for agent tools, this handover on main, and a test that checks the docs against the code.

Tags: every tag is annotated. `v1.1.5` object `da42a9269f9b96d50e0764c33385228f37f88dcd` points to `57d7e85`. `v1.2.0` object `71eb70b7ef5b52c13c3a6d8adc71576235c20d36` points to `6223659`. Check any tag with `git rev-parse vX.Y.Z` and `git rev-parse vX.Y.Z^{commit}`.

v1.2.0 commits on top of v1.1.5: `a568a61`, `8b3c24b`, `ef54e9f`, `c92d5a4` (writing work), `4060fd9` (catalog crash), `80545e1` (answer image before an empty marker), `d93336a` (ligature repair), `20724a4` (README repo path), `2a836cb` (exam length never from the extra-time rule), `0338c35` (links with a fragment), `8f0649c` (DRAG DROP items), `6223659` (package guard, text fixes, version 1.2.0).

CI for v1.2.0: branch run `43003300579` (workflow_dispatch, 4 jobs success) and main push run `43003567717` (4 jobs success). Tests at v1.2.0: 94 tests OK on Python 3.11 and 3.13.

## 3. Current state

### SC-900 real-data run (v1.2.0, 2026-11-11)

Owner files came from a shared Google Drive folder with one PDF and one VCE. The folder had no owner sheet, so a one-row sheet (vendor row plus the code row with the Drive link) was built and noted in the report.

- Workspace: `/workspace/runs/v120-real` on the box (not in git).
- Owner PDF sha256 starts `b11b97c4`. The VCE was skipped (binary, not decrypted), sha256 starts `ff730dad`, listed in REVIEW.md.
- Bank: 253 imported, 0 held, 0 researched, 0 answer_not_found, 11 owner keys flagged for the owner: `key_wrong` q003, q027, q142, q223, q248; `key_outdated` q088, q153; `key_arguable` q140, q187, q222, q227.
- Types: single_choice 89, inline_dropdown 72, yes_no_matrix 64, multiple_select 19, drag_drop 9.
- Gates: validate 64 of 64 ok; check_bank 10854 passed, 0 failed; conformance exit 0; writing round 2, 0 flags.
- Text fixes: 2 `lost_ligature` (q078 "unied" to "unified", q165 "verication" to "verification"). Key identity sha256 `5aefd6b240cded8d905d3dd51aa433d8dda796ccb035cdfc5c4b2fa7e9306c51`, identical before and after.
- Package: `SC-900-package.zip`, 18,857,881 bytes, sha256 `73941d06a0eeb906fd50658a8b694667ec1d455c7fdff07a5e2f485f9b9ade8a`. Scan: 610 members, 320 text files scanned, 290 images skipped, 0 denylist hits.

### Earlier exams

- Data-Con-101 (Salesforce): complete draft package with v1.1.4, verified from a GitHub install on the owner's Windows PC with v1.1.5.
- AB-730 (Microsoft): researched key regression for q089 (official screenshot plus page quote), kept as a test.

### Demo

`python tests/demo_kit.py microsoft DIR` and `python tests/demo_kit.py salesforce DIR` build synthetic workspaces that pass every gate offline (6 items, validate 64 of 64, check_bank 429 passed, package 0 denylist hits). The training exercises use them.

## 4. How to run, test and release

- Run one exam, a vendor batch or offline: operator guide section 9.
- Tests: `python -m unittest discover -s tests -v` on Python 3.11 and 3.13.
- Release: operator guide section 11.3. Branch, tests on 3.11 and 3.13, push the branch with a one-off `http.extraHeader` built from `GITHUB_TOKEN` (never printed or stored), trigger `tests.yml` by `workflow_dispatch` for the branch, wait for 4 green jobs, `git merge --ff-only` into main, annotated tag, push main and the tag without force, confirm the main CI run is green.

## 5. Lessons learned

Read `reference/lessons-learned.md` before every exam. The list below is the history in short form.

### Rules and gates (carry these every run)

- Re-read the latest owner instructions and `config/pipeline.yaml` before catalog, research, author, pages, bank, or validate. Rules can change mid-run.
- Official vendor brands are required. CertPassly is the site brand. Seller brands, social links, emails, phone numbers, free-update lines, and competitor names are banned in outputs (denylist gate).
- Never invent questions. Never invent or "fix" an answer key. If the owner file has no key, research official pages. If there is still no verbatim official evidence, flag `answer_not_found` and exclude it from scoring. Do not hold the item just for that.
- Official facts come from saved, hashed vendor pages, not from seller covers. Every fact needs a source id, url, sha256, and quote.
- Script first. Batch AI. The runner does not call a model.
- Nothing in `scripts/` is hardcoded to one exam or vendor, except `adapters/microsoft.py`. New vendors get an adapter or use `generic.py`.
- Sheet versus Drive mismatches go to `review.csv`. Do not invent or drop a file silently.
- Do not use em dashes or en dashes in pages, shared blocks, titles, or descriptions. Use a comma, a colon, a hyphen, or the word "to".
- The app has no Twitter, og:image, or last-checked columns. Those go in `page_meta_extras.csv`.
- Course JSON-LD belongs on the study-guide page only. The practice-test page must not emit Course. FAQPage may only include sourced answers.
- Stage order that keeps import files stable: pages, then import, then bank, then validate (manifest refreshed after bank).
- Freeze `CERTPASSLY_DATE` when you need reproducible last-updated stamps.
- Vendor and certification pages are built once and skipped when inputs are unchanged.
- Question types must stay distinct (yes/no matrix and multiple-select are not the same). The 30 types live in `reference/site-format/v1/question_types.json`.
- The owner works in Windows PowerShell. `install.ps1` is the native installer.
- If a zip will not open from a chat download, copy it to the Desktop and unzip from there.

### What worked on the first finished exam

- `check_bank` and `validate.py` passed on the bank that existed then (later gates were added on top).
- Official settings beat cover-page numbers.
- A weaker early pilot failed meta-length checks, used typographic dashes, and used a URL path that is not the live contract. Do not copy that pilot.

### v1.0.1 to v1.0.2

- Every third-party import must be listed in `pyproject.toml` and `requirements.txt`.
- A stage that only prints "write this file by hand" is a defect. Fix the script and add a test.
- Do not let a gate pass only because the first exam's author hand-wrote HTML. Tables render from research rows.
- Vendors that do not publish a pass mark are normal. Never print Python `None` on a page.
- Never hardcode counts or names from one exam in report text.
- Generic official-page parsing must work per block line, with plural units and capitalised labels. Tests cover "105 minutes", "Languages: English", and "Name (40-50%)".
- JavaScript vendor pages can give an empty plain fetch. Save a rendered copy with sha256, or every fact becomes a gap.
- Windows: assume a legacy code page. The CLI forces UTF-8 mode. Tests read and write with `encoding="utf-8"`. Tesseract may be missing.
- CI must show 0 skipped. Optional suites are not collected when their data is absent. Real owner extracts never go into git.

### v1.1.0 (real Data-Con-101 run, AB-730 q089)

- Salesforce exam guides are JavaScript pages. A plain fetch returned 62 text characters. Render with headless Chromium when the text is short.
- "Passing score: 70%" has the same shape as "Solution Positioning: 14%". Fact labels are never domains. Weights must sum to about 100.
- "maintainable" once matched a renewal regex. Match whole words (renewal, recertification, maintenance) and require a time period or expiry in the sentence.
- Sidecars store absolute paths. A copied workspace must resolve them next to the sidecar, or offline reruns silently miss saved pages.
- A SystemExit with a message must be logged. "exit 1" alone hides the reason.
- Bordered answer-area boxes can have one faint edge. Accept three dark edges plus the faint one at a lighter threshold so region coordinates come from the script, not from AI.
- A no-answer item can be answered from an official screenshot as well as text (AB-730 q089). Save the screenshot with sha256. The verifiable quote must still be page text.
- Web search from scripts is often blocked. Always seed `answer_research` with the exam's official sources and listed URLs. Log a failed search.

### v1.1.1 to v1.1.3 (CI)

- Python 3.11 is the oldest supported version. Never reuse the outer quote type inside an f-string expression. Run `py_compile` on 3.11 before pushing. (v1.1.1, CI run 42975699520)
- Path filters must normalise `os.sep` to `/` before matching. (v1.1.2, CI run 42976175004)
- Paths written into JSON or evidence must be POSIX `/`, never `os.sep`. (v1.1.3, CI run 42976591708)

### v1.1.4 (Data-Con-101 author through package)

- Official skill weights are not always `Name (min-max%)`. Salesforce uses `Name: 14%` for a single figure. Accept both forms (and an en dash in a range, after normalisation).
- If the vendor publishes a price or question count, use it. Site choice is only for a gap. Validate 12c must follow that rule.
- Author-stage prose must clear word-count and grade gates (150+ words, grade 11 or lower). Short sentences lowered a study-guide grade from 11.9 to 8.6. Vendor and cert pages needed a few more plain sentences to clear 150 words.
- `check_import_conformance.py` can prove import files match the published contract, including the new fields. It cannot prove the live site importer accepts them until the site team runs their importer.
- Live Drive: a public "anyone with the link" folder returns HTTP 200 and resume works by sha256. A folder id that is not shared returns HTTP 404 and a clear script message.

### v1.1.5 (Windows GitHub-install verify)

- `find_saved` remapping sidecar paths is not enough. Any reader that opens `meta['path']` or `meta['text_path']` from a sidecar must use the same helper. A copied workspace failed research on Windows with "no skill outline with weights" even though the rendered exam-guide HTML and sha256 were present.
- Poppler version matters more than Tesseract for text-layer PDFs. Windows Poppler 25.07.0 `pdftohtml -xml` kept XML document order correct but wrote unusable `top` attributes (collapsed duplicates; some markers near the page max). A global `(page, top, left)` sort then assigned options and "Correct Answer:" to the wrong items and left `answer_raw` empty, so `answer_research` treated almost every item as unanswered. Trust XML order when tops collide or look flipped. Keep the Y-sort only when coordinates are consistent, so a same-line letter to the right of "Correct Answer:" still attaches. Normalise CRLF even when a given dump is LF-only.
- Do not check owner-exam `raw.xml` into git. Synthetic pdf2xml fixtures must reproduce the coordinate problem.

### v1.2.0 (SC-900)

- The seller brand appears in owner PDFs and survives in raw extracts. Raw extracts never ship; the package stage scans every file in the zip against the config denylist and deletes the zip on any hit. Reports name the rule number, never the term.
- Glued brand names (two words written as one) must be caught by token start and end matching, not only whole words.
- Lost ligature glyphs ("unied", "verication") are common in text-layer PDFs. Repair known words by script, propose the rest, and prove keys and option order did not change.
- Typo and article rules must be tight: skip inflections, use vowel sounds for acronyms and words that start with "u", and protect every capitalized word and every word on the saved official pages.
- A DRAG DROP marker means `drag_drop` with tiles and targets, even when the picture looks like blanks.
- Exam length must never come from the extra-time rule.
- One run per exam folder. Two runs on one `out/<CODE>/` overwrite each other.
- A Drive folder without an owner sheet is normal. Build a one-row sheet and say so.

## 6. Open items

1. **Site importer fields.** The site importer must accept `answer_key_status` values `researched_unverified` and `answer_not_found`, plus `key_source`, `verification_status` and `scoring_excluded_question_keys`. The pipeline writes them; the site team has not run the live importer on these packages. Do not change site code from this repo.
2. **Link-check cache.** Offline validate (gate 09c) needs `cache/linkcheck.json`. Include it when you pack inputs for another machine, or run validate online once.
3. **Direct script calls.** `certpassly-pipeline` sets the workspace root and UTF-8 mode. A bare `python scripts/validate.py` needs `CERTPASSLY_ROOT` and, on Windows, `PYTHONUTF8=1`. Adding `encoding="utf-8"` to every `open()` call is still to do.
4. **ResourceWarnings.** Some scripts open files without a `with` block. Clean them up when you touch a file. Not a release blocker.
5. **Remaining exams.** Run the rest of the owner sheet in vendor batches (`--vendor SLUG --batch`). After each batch: validate, check_bank, conformance, package, and a report with proof (operator guide section 13).
6. **No run lock.** Nothing stops two runs on one exam folder. Operators must check first (operator guide section 10). A lock file would be a small, safe addition.
