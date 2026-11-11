# HANDOVER.md

Full guidance for the CertPassly exam pipeline skill. Read this if you need to run the skill, push a change, or pick up the v1.2.0 writing work. Plain English. No typographic dashes.

This document lives on branch `docs/handover-v1.2.0-plan`. It is not a product release. Do not merge it to `main` until the team reviews it.

## 1. What the skill is and how it works

The skill is a scripts-first pipeline named `certpassly-exam-pipeline`. The command is `certpassly-pipeline`. It builds draft CertPassly exam pages and question import files from official vendor sources and the owner's question PDFs.

It never talks to the site app, artisan, or the site GitHub repo. Site rules are a snapshot under `reference/site-format/v1/`.

Official vendor brands only (for example Salesforce, Microsoft). CertPassly is the site brand. Never invent questions. Never invent answer keys. Draft records only. Max scripting, min AI.

### Stage order

Stages always run in this order. Use `--list-stages` to print the same table.

1. `catalog` (script). Builds `catalog.csv` and `review.csv` from the owner exam sheet. It can check official exam URLs. That check is skipped when a saved copy already exists.
2. `intake` (script). Inventories Drive folders, downloads owner files, runs provenance, writes `out/<CODE>/intake/`. Network is for Drive only. Offline skips the download and uses files already in `owner-files/`.
3. `sources` (script). Fetches and hashes official vendor pages listed in research JSON. Reuses saved copies. JavaScript pages may be rendered with Playwright when a plain fetch has almost no text, or when the vendor sets `render: true`.
4. `research` (script first). Fills or checks research JSON from official pages using a vendor adapter in `scripts/adapters/`, chosen from `config/vendors.yaml`. AI is allowed only for official facts the adapter lists as gaps, and only with a quote and a source id. This is not the author stage.
5. `extract` (script). Splits the owner PDF with Poppler, writes item JSON, and writes a visual draft from OCR and marker boxes when it can. No AI. If Tesseract is missing, OCR is skipped and the author stage transcribes later.
6. `answer_research` (script, pick later). For items with no answer in the owner file, it finds candidate official pages, saves them with sha256, and ranks matching lines. The key is picked in the author batch file `authoring/answer_research.json`. A script then re-checks: official domain, saved copy, verbatim quote. No evidence: the item stays a draft flagged `answer_not_found` and is excluded from scoring. Items are never held just because the owner file had no key, and keys are never invented.
7. `author` (THE ONLY MARKED AI STAGE). One batched pass. It rewrites explanations, writes original page prose (`page_prose.json`), finishes visual transcription when OCR is not enough, writes `bank_meta.json`, and can pick researched keys in `answer_research.json`. It must not invent questions and must not change stems, options, or keys. `run_pipeline.py` does not call a model. It only checks that the required authoring files are present and stops with instructions if they are not.
8. `pages` (script). Builds exam pages, plus shared vendor and certification pages, from research JSON and `page_prose.json`. Vendor and cert pages are skipped when their inputs have not changed.
9. `import` (script). Writes workbook CSVs, sidecars (including `page_meta_extras.csv`), and `simulator_settings.json`.
10. `bank` (script). Assembles `questions.json`, question import CSVs, media, `CLEANUP-LOG.md`, and `REVIEW.md`. It runs after import so page `sources.csv` is merged, not wiped.
11. `validate` (script). Refreshes `MANIFEST.json`, then runs `validate.py` and `check_bank.py`. Exit 1 on any failed check.
12. `package` (script). Zips the exam package plus the shared vendor and certification pages.

Only step 7 is the marked AI stage. Everything else is a script. Keep AI batched. Do not call a model from the runner.

## 2. Folder map

Skill repo root (this repository):

- `SKILL.md` and `SKILL_BODY.md`: the skill text. A test requires them to stay identical.
- `README.md`: install and quick start.
- `CHANGELOG.md`: version history.
- `HANDOVER.md`: this file.
- `pyproject.toml`: package name `certpassly-exam-pipeline`, entry point `certpassly-pipeline`, version.
- `install.sh` and `install.ps1`: Linux or macOS, and Windows, installers.
- `config/pipeline.yaml`: brand, disclaimer, denylist, banned phrases, shared-block cap, site format version. Re-read this before catalog, research, author, pages, bank, or validate.
- `config/vendors.yaml`: which adapter to use, and flags such as Salesforce `render: true`.
- `config/catalog_overrides.json`: exam-specific labels. Scripts must not hardcode exam names.
- `scripts/run_pipeline.py`: the orchestrator.
- `scripts/adapters/generic.py`: Salesforce and the fallback official-page parser.
- `scripts/adapters/microsoft.py`: Microsoft official-page parser.
- `scripts/fetch_sources.py`: fetch, hash, sidecars, and `load_sidecar` / `resolve_sidecar_paths`.
- `scripts/render_page.py`: optional headless Chromium render.
- `scripts/research_init.py`: scripted research JSON from catalog and official pages.
- `scripts/extract_owner_pdf.py`: owner PDF split and layout.
- `scripts/answer_research.py`: official-page candidates for items with no owner key.
- `scripts/build_pages.py`, `scripts/emit_import.py`, `scripts/build_bank.py`: pages, import CSVs, bank.
- `scripts/validate.py`, `scripts/check_bank.py`, `scripts/check_import_conformance.py`, `scripts/manifest.py`: gates and the site-format contract check.
- `scripts/drive_fetch.py`, `scripts/drive_inventory.py`, `scripts/drive_crawl.py`: Drive intake.
- `scripts/build_catalog.py`: catalog from the owner sheet.
- `reference/site-format/v1/`: the frozen site contract. Includes `question_types.json`, `csv_templates/`, `url_routes.json`, `allowed_statuses.json`, and the simulator schema. The pipeline must use this folder, never a live app checkout.
- `reference/lessons-learned.md`: lessons from real runs. Read before every exam.
- `shared/`: shared page blocks, capped by config (default 40 percent of a page body).
- `tests/`: unit, gate, demo, and regression tests (`test_v110.py`, `test_v114.py`, `test_v115.py`, `test_demo_end_to_end.py`, `test_ab730_regression.py`, and others).
- `.github/workflows/`: GitHub Actions, Ubuntu and Windows, Python 3.11 and 3.13.

A workspace (the `--root` folder, not the skill repo) holds `catalog.csv`, `sheet.csv`, `config/`, `owner-files/`, `sources/`, `research/`, `out/<CODE>/`, `cache/`, and `run.log`. Authoring files live in `out/<CODE>/authoring/`.

## 3. Exact commands

Run these from a machine that has Python 3.10 or newer (3.11 and 3.13 are tested). On Windows use PowerShell and `install.ps1`. Quote paths that contain backslashes.

### Install

```
git clone https://github.com/msaqlainhaneef1/certpassly-exam-pipeline.git
cd certpassly-exam-pipeline
git checkout v1.1.5
python -m venv .venv
```

Linux or macOS:

```
source .venv/bin/activate
pip install -e .
# optional, only if you must render JavaScript official pages:
pip install -e ".[render]"
python -m playwright install chromium
```

Windows PowerShell:

```
.\.venv\Scripts\Activate.ps1
# or use install.ps1
pip install -e .
```

Check the CLI:

```
certpassly-pipeline --help
certpassly-pipeline --list-stages
```

### Run one exam end to end

```
certpassly-pipeline --exam Data-Con-101 --root C:\path\to\workspace --sheet C:\path\to\workspace\sheet.csv --date 2026-11-11
```

`--date` freezes last-updated stamps (also honors `CERTPASSLY_DATE`). Repeat `--exam` for more than one code. Use `--vendor salesforce` for every exam of that vendor, `--all` for the whole catalog, or `--batch` for catalog (sheet) order.

### Run one stage (repeatable)

```
certpassly-pipeline --exam Data-Con-101 --root C:\path\to\workspace --sheet C:\path\to\workspace\sheet.csv --stage research --stage extract
```

Default is all stages. Failed checks exit with status 1 and later stages do not run.

### Offline mode

```
certpassly-pipeline --exam Data-Con-101 --root C:\path\to\workspace --sheet C:\path\to\workspace\sheet.csv --offline --date 2026-11-11
```

No network. Uses saved sources and `cache/linkcheck.json` only. For a fair offline validate, that cache file must be in the workspace. If you pack inputs for a later machine, include `cache/linkcheck.json`.

### Validate, bank, and site-format check

Set `CERTPASSLY_ROOT` to the workspace. On Windows, if you call the scripts directly, also set UTF-8 mode (see Windows notes).

```
# from the workspace, with the skill's scripts on PYTHONPATH or from the venv install
python scripts/validate.py research/salesforce/Data-Con-101.json --offline
python scripts/check_bank.py out/Data-Con-101 --registry reference/site-format/v1/question_types.json
python scripts/check_import_conformance.py out/Data-Con-101
```

`check_import_conformance.py` checks import files against `reference/site-format/v1` (CSV templates, question types, allowed statuses, simulator schema, including `key_source`, `verification_status`, `researched_unverified`, `answer_not_found`, and `scoring_excluded_question_keys`). It is not a live site-importer run.

Prefer `certpassly-pipeline --stage validate` so UTF-8 mode and the manifest refresh happen for you.

### Tests

From the skill repo:

```
python -m unittest discover -s tests -v
```

At v1.1.5 this is 55 tests, exit 0, on Python 3.11 and 3.13. The gold exam suite runs only when `CERTPASSLY_GOLD` is set. It is not collected in CI (0 skipped). Do not put real owner extracts into git. Use the synthetic fixtures under `tests/`.

### Windows notes

- The CLI re-runs itself with `PYTHONUTF8=1` and `-X utf8` when the locale is not UTF-8, and child scripts get `PYTHONUTF8=1`. Official pages stay readable (typographic apostrophes, en dashes in weight ranges).
- If you invoke `validate.py` (or other scripts) with a bare `python` on Windows, set the same env yourself, or check 02 can fail: the research JSON is UTF-8, Windows default `cp1252` turns U+2019 into mojibake, and the quote is not found on the UTF-8 page. This is a footgun. The CLI already handles it.
- Install Poppler and put it on PATH. The GitHub-install PC used Poppler 25.07.0. Tesseract may be missing; then OCR is skipped and author transcribes.
- Poppler 25.07.0 `pdftohtml -xml` can emit bad `top` values. v1.1.5 already works around that. Do not sort a raw dump by `top` yourself.
- Sidecars store absolute paths. v1.1.5 remaps them to the file next to the sidecar. Do not hand-edit sidecars as a workaround.
- In PowerShell, quote paths. Do not use bash `source` unless you are in Git Bash.
- Paths written into JSON or evidence must use forward slashes, never `os.sep`.
- Python 3.11 cannot nest the same quote type inside an f-string expression. Run `python3.11 -m py_compile` on changed scripts before you push.

## 4. Release and push flow

The box cannot push to the private GitHub repo. The owner's PC can (`gh` as `msaqlainhaneef1`). The safe path is a git bundle.

### On the box (skill repo)

```
cd /home/box/agent-data/workflows/certpassly-exam-pipeline
# commit on a branch if that is the review path; or on main only when a release is agreed
git status
# create an annotated tag only for a release, for example:
# git tag -a v1.1.5 -m "v1.1.5: short summary"
git bundle create /tmp/my-change.bundle v1.1.5..HEAD
# or, for this docs branch:
git bundle create /tmp/handover-v1.2.0-plan.bundle v1.1.5..docs/handover-v1.2.0-plan
```

Copy the bundle to the PC, for example to `C:\Users\Saqlain\AppData\Local\Temp\`.

### On the PC

Use the existing clone at `%TEMP%\certpassly-exam-pipeline` if it already has `v1.1.5` or `main`. Do not rewrite tags. Do not force-push.

```
cd $env:TEMP\certpassly-exam-pipeline
git fetch origin
git fetch C:\Users\Saqlain\AppData\Local\Temp\handover-v1.2.0-plan.bundle docs/handover-v1.2.0-plan:docs/handover-v1.2.0-plan
# for a main release instead, you would: fetch the bundle, checkout main, git merge --ff-only, then
# git push origin main v1.1.x
# For this handover, push the branch only:
git push origin docs/handover-v1.2.0-plan
```

Do not push `main`. Do not push tags unless you are cutting a release that was agreed.

### Watch CI

```
gh run watch
# or
gh run list --branch docs/handover-v1.2.0-plan
gh run watch <run-id>
```

CI matrix (`.github/workflows/`):

- `ubuntu-latest` and `windows-latest`
- Python 3.11 and Python 3.13
- Four jobs. All must pass.

If CI fails, fix it on a follow-up commit, bump the version only when you are releasing (`v1.1.6` style), and push again. For this docs branch, fix the branch and push the branch only.

### Tags already cut

- `v1.0.0` first packaged release
- `v1.0.1` declare image deps and add CI
- `v1.0.2` demo-run fixes
- `v1.1.0` answer_research and real-run fixes
- `v1.1.1` Python 3.11 f-string
- `v1.1.2` Windows denylist path filter
- `v1.1.3` POSIX evidence paths
- `v1.1.4` Data-Con-101 through package, conformance check
- `v1.1.5` Windows sidecar remap and pdftohtml tops (commit `57d7e852fd878313e9b70efa5e96aba3d0e53fa7`, tag object `da42a9269f9b96d50e0764c33385228f37f88dcd`)

## 5. Current state

Current release on `main` is **v1.1.5**. This branch only adds `HANDOVER.md`.

### Versions and what each one fixed

- **v1.0.0**: First packaged skill. Scripts-first runner, one AI stage (`author`), site-format snapshot, vendor adapters, shared blocks, owner PDF extract, validate gates, install entry point.
- **v1.0.1**: Declared numpy, OpenCV, and Pillow so extract works on a clean CI runner. Added the GitHub Actions matrix (Linux and Windows, 3.11 and 3.13).
- **v1.0.2**: Demo runs on two synthetic exams found real gaps. Intake now writes `files.json`. Catalog keeps an existing `catalog.csv` when no sheet is passed. Pages render sourced tables when prose has none. Unpublished facts say "not published by the vendor". Validate 01c accepts a missing pass mark when research records the reason. Bank no longer crashes on a missing key (later replaced by answer_research). OCR survives a missing Tesseract. The CLI forces UTF-8 mode on Windows. Gold tests are opt-in. Demo end-to-end tests added.
- **v1.1.0**: No-answer items are never held. New `answer_research` stage. Researched keys are `researched_unverified`. No evidence is `answer_not_found` and is excluded from scoring. Drive download, scripted research JSON, Playwright render, catalog overrides. Fixes from the real Data-Con-101 run (pass-mark parsed as a domain, "maintainable" as renewal, sidecar paths, hidden SystemExit). AB-730 q089 imported from an official Microsoft page. The site importer must accept the new status fields.
- **v1.1.1**: Python 3.11 SyntaxError in `build_bank.py` (nested f-string quotes) that failed all four CI jobs.
- **v1.1.2**: Windows denylist scan used forward slashes only and flagged a stripped-text audit file.
- **v1.1.3**: `answer_research` saved paths with backslashes. Evidence paths are always written with `/`.
- **v1.1.4**: Salesforce Data-Con-101 finished through author (one batched pass: 65 short explanations and page prose), pages, import, bank, validate, check_bank, and package. 65 imported, 0 held, 62 of 62 validate checks passed, check_bank 2841 passed and 0 failed. Validate check 02 accepts a single weight like `Solution Positioning: 14%`. Official price and question count are used when the vendor publishes them. New `check_import_conformance.py`.
- **v1.1.5**: Windows sidecar `path` / `text_path` remap is shared (`load_sidecar`) so a copied workspace can research official weights without a hand edit. Owner PDF extract keeps keys when Poppler 25.07.0 `top` values are unusable. Tests in `tests/test_v115.py`.

### CI that passed for v1.1.5

Run: https://github.com/msaqlainhaneef1/certpassly-exam-pipeline/actions/runs/42984585915

Overall: success.

- windows-latest, Python 3.13, job id 130402618871, about 1 minute 14 seconds, success
- windows-latest, Python 3.11, job id 130402619198, about 1 minute 15 seconds, success
- ubuntu-latest, Python 3.11, job id 130402619239, about 31 seconds, success
- ubuntu-latest, Python 3.13, job id 130402619241, about 33 seconds, success

Annotations were only the Node 20 / ubuntu-latest migration notices. No v1.1.6 retry was needed.

### AB-730

Microsoft exam work in v1.1.0. Item q089 (`active_screen`) was imported with key r2, "the Sources information icon", from the official learn.microsoft.com page on managing public web access. Confidence was high and the record is still unverified. The verifiable quote is page text. The screenshot is saved with sha256. Regression: `tests/test_ab730_regression.py`. This is not a claim that every AB-730 item is packaged the same way as Data-Con-101.

### Data-Con-101 (box, v1.1.4 then verified with v1.1.5)

On the box workspace `/workspace/runs/dc101`:

- 65 questions imported, 0 held, scoring excluded empty
- All keys `answer_key_status=as_in_source_file`, `key_source=owner_file`
- Validate 62 of 62
- check_bank 2841 passed, 0 failed
- Package sha256 `407e68c6aa28f6ebdf6b3e0f81ee240d5cae789753a2691543c0b50f016d92a8` (239987 bytes)
- `questions.json` sha256 `1539d540e407c230cb4850f2bedfa30733a57471dd67d8f50c5fb16f3bfe972b` (236160 bytes, LF)
- `import/questions.csv` sha256 `872fa80fc4d980949ebea2c095a1d972ad4f4c11defea83debb8d2eb4848e0b7` (38623 bytes)
- Exam-guide HTML sha256 `81a7ea5df2fccd4643d3c6d2a6f873410e142113adfdf523ea510eae2ca04277`, method: rendered with headless Chromium (only 62 text characters in a plain fetch), retrieved `2026-11-11T05:24:32+0500`
- Six domain weights: 14, 13, 18, 17, 18, 20

### GitHub verification on the owner's Windows PC

Goal: prove the skill works when installed from GitHub, on the real Data-Con-101 exam, with zero AI calls.

v1.1.4 first try failed on two Windows bugs (sidecar paths, then dropped owner keys). Those were fixed in v1.1.5.

v1.1.5 re-verify (2026-11-11, Asia/Karachi):

- Fresh clone of tag v1.1.5 at commit `57d7e85...`, venv Python 3.11.9, `pip install` exit 0
- Same packed inputs, **no** manual sidecar path rewrite, **no** new AI (authoring files already present)
- Research found 6 domains without remapping sidecars
- Extract kept owner keys; author ran; 65 imported, 0 held
- First pipeline stop was validate 09c: `cache/linkcheck.json` was not in the input pack (not a skill logic bug)
- A bare `python validate.py` without `PYTHONUTF8` also showed check 02 mojibake. The CLI with UTF-8 mode passes check 02
- After the box link-check cache was copied in (`sha256 14316563671cb628fc9f996fa42b23ee65c0ff18cbe8564b7de9fcd370e4ebf6`), `certpassly-pipeline --stage validate --stage package` exited 0
- Validate 62 of 62, check_bank 2841 passed and 0 failed (same as the box)
- Site banned-term hits: 0
- PC package sha256 `1c423d3b32ebfad6b38a5728ab4ffa7c2f78995f42d6c64bc60f239bd884718a` (239639 bytes)
- Compare vs box outputs: 29 raw sha256 matches, 92 raw diffs, 0 only-PC, 0 only-box. Of the 92, 84 are CRLF versus LF only, including `questions.json`. `import/questions.csv` is a raw byte match. The other 8 are expected: Windows absolute paths, validate clock text, Poppler 25.07.0 versus 25.03.0 raw XML and cover cleanups, manifest hashes, one certification boilerplate sentence, and the package zip as a whole
- Proof write-up: `C:\Users\Saqlain\OneDrive\Apps\Desktop\certpassly-git-verify\` and `/workspace/deliverables/git-verify/` (`GIT-VERIFY.md`, `live.log`, `compare-results.json`, the PC package zip)

Live Drive re-fetch was not run in that verify. The site's live importer was not run. Site code was not changed.

## 6. Lessons learned

Read `reference/lessons-learned.md` before every exam. The short list below is the full set of lessons, including Windows.

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

## 7. Open items

1. **Site importer fields.** The site importer must accept the new `answer_key_status` values and related fields: `researched_unverified`, `answer_not_found`, `key_source`, `verification_status`, and `scoring_excluded_question_keys`. The pipeline already writes them. The site team has not run the live importer on these packages. Do not change site code from this skill repo.
2. **Link-check cache in the input pack.** Offline validate check 09c needs `cache/linkcheck.json`. The Data-Con-101 verify pack omitted it, so package did not run until the box cache was copied in. When you pack inputs for another machine, include that cache (or run validate online once to build it).
3. **`validate.py` UTF-8 footgun.** `certpassly-pipeline` forces UTF-8 mode. A bare `python validate.py` on Windows uses `cp1252` unless `PYTHONUTF8=1` is set, and check 02 can fail on typographic apostrophes. A later fix can add `encoding="utf-8"` to those `open()` calls. Not done in v1.1.5.
4. **ResourceWarnings.** Some scripts still open files without a `with` block. Python may print `ResourceWarning: unclosed file` in tests or verbose runs. Clean those up when touching the file. Not a release blocker.
5. **Remaining exams.** Data-Con-101 is complete as a draft package (and verified from GitHub on Windows). AB-730 has a researched key regression for q089, not a full "verified from GitHub" package story like Data-Con-101. The rest of the owner sheet still needs to be run in vendor batches (`--vendor` or `--batch`). Same rules: official brands only, no invented keys, author is one batched AI pass, then scripts through package. After each vendor batch, validate, check_bank, conformance, and package. Push only when the team agrees.

## 8. The v1.2.0 plan

Goal: make page and explanation writing consistent, people-first, and hard to mistake for generic AI text. Keep the pipeline scripts-first. Do not copy competitors. Do not invent facts or keys.

v1.2.0 is a planned skill release. It is not tagged yet. Do this work on a branch, with tests, then release only when the acceptance list below is green.

### 8.1 Writing brief (add this to the skill)

Put a short writing brief in the skill (for example a section in `SKILL.md` plus `reference/writing-brief.md`). The author stage and any human writer must follow it. Keep the brief itself in the same style.

Rules for the brief:

- Plain, friendly English.
- Short sentences. Prefer one idea per sentence.
- No jargon unless the official vendor page uses that term, and then explain it in plain words the first time.
- No typographic dashes (no em dash, no en dash). Use a comma, a colon, a hyphen, or the word "to".
- Write for people first, not for search engines. Follow Google's people-first guidance: helpful, reliable, original content that satisfies the search. Show first-hand use of the official pages (quotes, source links, checked dates). Do not write a page just to rank. Do not stuff keywords. Do not copy other sites.
- After writing, run a self-check (see 8.5) before the files are treated as done.

### 8.2 Banned AI-phrase list (good and bad examples)

Keep the list in `reference/writing-brief.md` and, where useful, as data the scripts can load (for example `config/banned_ai_phrases.txt` or a YAML list). Start with at least these. Add more when a run finds a new stock phrase. The list is about wording, not about official vendor terms.

Bad (do not use) -> Good (use something like this):

- "In today's digital world, data is more important than ever." -> "This exam tests how you use Data 360 at work. The official guide lists the skills below."
- "Unlock your potential and take your career to the next level." -> "The credential is earned by passing the official exam. The vendor states the requirements on the page we saved."
- "This comprehensive guide will delve into everything you need to know." -> "This page covers the official exam facts, the skill outline, and a study plan. Every figure has a source link and a checked date."
- "Whether you are a beginner or an expert, this is for you." -> "The official page lists the experience the vendor expects. We quote that wording and do not add our own levels."
- "Leverage a robust, seamless, cutting-edge solution to empower your team." -> "Use the official product name and say what the task is, in the same words the vendor uses where you can."
- "It is important to note that..." / "Moreover..." / "Furthermore..." / "Additionally, it should be noted..." -> Just state the fact. "The official passing score is 70 percent."
- "Dive in" / "Let's dive in" / "Let's get started on this journey." -> "Here is the official outline." or "Start with domain 1."
- "The landscape of certification is constantly evolving." -> "The vendor can change the exam. We re-check the official page and show the date we checked."
- "In conclusion, ..." as a filler wrap-up -> Close with the official next step, or with what the reader should do (book the exam only from the vendor, bring proof of the official result).
- "Unlock the power of..." / "This game-changer..." / "Holistic approach" -> Name the concrete skill or task from the outline.

Official product names, exam codes, and quoted vendor sentences are allowed even if they sound formal. Do not rewrite a verbatim quote to dodge the list.

### 8.3 New scripted inputs: search intent, and competitor notes as topics only

Add a scripted input step before (or at the start of) pages and author, so writers are not guessing what people ask.

**Search-intent file** (workspace, not invented in prose): for example `research/<vendor>/<CODE>.search-intent.json` or `out/<CODE>/authoring/search_intent.json`. A script suggests:

- The main query the exam hub, FAQ, objectives, study guide, and practice-test pages should answer.
- People-also-ask style questions, drawn from obvious official facts (duration, passing score, renewal, skills measured) and from gaps the research file already recorded.
- Which page should answer which question.

A person can edit the file. The script must not scrape a private or unofficial bank. It must not invent official numbers.

**Competitor-notes input** from the CertPassly Researcher: for example `research/<vendor>/<CODE>.competitor-notes.json`. Use this as **topics only**. Never copy sentences, titles, outlines, or explanations from it into our pages. The script records topic labels (for example "renewal steps", "what the exam is not"). The author may cover a topic only if our official sources support it. If a topic is not on a saved official page, skip it or say the vendor did not publish it. A gate must fail the run if a page copies a long phrase from the competitor notes.

### 8.4 Scripts check the result; only flagged parts get fixed

After authoring and pages:

1. Scripts run the existing gates (word count, grade, banned filler, typographic dashes, denylist, quote-on-saved-page, uniqueness, and so on).
2. New checks use the writing brief: banned AI phrases, sentence-length hints, search-intent coverage (each PAA-style question is answered on the planned page, with a source when it is a fact), and a competitor-overlap scan (no copied wording).
3. The script writes a findings file, for example `out/<CODE>/writing-review.json` and a short `WRITING-REVIEW.md`.
4. Only the flagged parts go back for a fix. Do not rewrite whole pages that already passed. A second scripted check must run after the fix.
5. Unresolved flags stay in `REVIEW.md`. Do not mark records published or verified to clear a flag.

### 8.5 Self-check (writers and the skill)

Before an authoring batch is accepted, the writer (human or model) must confirm:

- Every official number and name matches the research file and a saved page quote.
- Short sentences, plain words, no typographic dashes.
- No phrase from the banned AI list, unless it is inside a vendor quote.
- Each page answers the search-intent questions assigned to it.
- Competitor notes were used as topics only. No copied wording.
- No invented key, no invented fact, no invented question.
- Grade and word-count gates still pass.

The skill should include this list in `reference/writing-brief.md` and have a script tick what it can tick automatically.

### 8.6 Files to change

- `SKILL.md` and `SKILL_BODY.md`: writing brief pointer, new input files, and the check-then-fix loop. Keep the two files identical.
- `reference/writing-brief.md`: the brief, Google people-first summary, banned-phrase list with good and bad examples, self-check.
- `config/` data for the banned-phrase list if the script should load it as data.
- `scripts/run_pipeline.py`: a stage or pre-step for search-intent and competitor-notes inputs; a writing-check step after pages (and after a flagged fix). Still no model call in the runner.
- New script(s), for example `scripts/search_intent.py` and `scripts/check_writing.py`.
- `scripts/build_pages.py` and the author-stage instructions: consume search-intent assignments; never paste competitor text.
- `scripts/validate.py`: optional thin wrappers so a failed writing gate can fail the run when configured.
- `CHANGELOG.md` and `reference/lessons-learned.md` when the work ships.
- `pyproject.toml` version bump to 1.2.0 only at release time.
- Tests listed below. Demo fixtures may need a tiny search-intent file and a competitor-notes file with a phrase that must not appear in output.

Do not hardcode an exam or vendor. Do not change site app code in this repo.

### 8.7 Tests to add

- Writing-brief file exists and has no typographic dashes.
- Banned-phrase checker flags the bad examples and allows the good examples, including a vendor quote that contains a formal phrase.
- Search-intent suggestion builds questions from research facts (duration, pass mark, outline) without inventing a number the research file does not have.
- A page that misses its assigned PAA-style question is flagged. A page that answers it is not.
- Competitor-notes wording copied into HTML or prose fails. A page that only covers the same topic in original words, backed by an official quote, passes.
- A findings file lists only failed checks. A clean run writes zero flags.
- Existing demo end-to-end and v1.1.5 tests still pass on Python 3.11 and 3.13, Linux and Windows.
- No typographic dashes in new docs or golden HTML fixtures.

### 8.8 Acceptance criteria for v1.2.0

- The writing brief is in the skill, in plain English, with the banned-phrase list, people-first rules, and the self-check.
- Search-intent and competitor-notes inputs are documented and scripted. Competitor notes cannot be copied into outputs.
- Scripts flag writing problems. Only flagged parts are sent back for a fix. A second check is required.
- Unit tests above are green. Full `unittest discover` stays green on the CI matrix (Ubuntu and Windows, Python 3.11 and 3.13).
- A real or demo exam run still imports the same stems, options, and keys (no writing change may alter a key). Validate and check_bank still pass.
- `check_import_conformance.py` still passes. New fields from v1.1.0 remain in the contract.
- CHANGELOG and lessons-learned are updated. The release is tagged `v1.2.0` only after CI is green.
- The site-importer open item can stay open; it is not a v1.2.0 writing blocker, but it must stay listed.

## How to use this branch

This branch is documentation and a plan. To review:

```
git fetch origin docs/handover-v1.2.0-plan
git checkout docs/handover-v1.2.0-plan
```

To start the v1.2.0 work, branch from current `main` (v1.1.5), not from this docs branch, unless you first merge the handover with a review:

```
git checkout main
git pull --ff-only
git checkout -b feature/v1.2.0-writing
```

Then follow section 8. Keep scripts first. Keep one batched AI author step. Do not invent keys. Do not copy competitors. Do not push `main` or tags until the acceptance list is met and the team agrees.
