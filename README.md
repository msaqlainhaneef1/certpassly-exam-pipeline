# CertPassly exam pipeline

A scripts-first skill that turns official vendor pages and owner question PDFs into draft, site-ready exam pages and question-import files for CertPassly.

Current version is `1.3.0`. The pipeline does not read the CertPassly application repository, run artisan, or call GitHub. Site contracts live in `reference/site-format/` (v1 workbooks and the site v2 exam schema).

Read [reference/lessons-learned.md](reference/lessons-learned.md) and [HANDOVER.md](HANDOVER.md) before you run a new exam. Config details are in [docs/question-type-rules.md](docs/question-type-rules.md), [docs/ocr.md](docs/ocr.md) and [docs/fidelity.md](docs/fidelity.md).

**AI agents and new operators:** start with [AGENTS.md](AGENTS.md), then read the full manual [docs/AI-OPERATOR-GUIDE.md](docs/AI-OPERATOR-GUIDE.md) (every rule, every stage, the author pass, runbooks, release flow, done checklist and report template) and do the exercises in [docs/AI-TRAINING-EXERCISES.md](docs/AI-TRAINING-EXERCISES.md). The writing brief for part 2 is [reference/writing-brief.md](reference/writing-brief.md).

## Two-part workflow

Part 1 is technical and is the default. It is scripts only: owner PDF to one site v2 exam file. No web, no AI, and no explanations.

```bash
certpassly-pipeline --exam EXAM-CODE --root /path/to/workspace --offline
```

Stages: `intake`, `extract`, `export`, `validate_site`, `package`.

Part 2 is the later content path: search, writing and AI.

```bash
certpassly-pipeline research --exam EXAM-CODE --root /path/to/workspace --offline
certpassly-pipeline verify --exam EXAM-CODE --root /path/to/workspace --offline
```

`research` runs catalog, intake, sources, research, extract, textfix, answer_research, intent, author, pages, writing, import and bank (intake and extract are reused when they already exist). `verify` runs the bank `validate` stage and `package`. The only AI stage is `author`, and it is batched. Part 2 uses [reference/writing-brief.md](reference/writing-brief.md): search intent, competitor notes as topics only, and the check-then-fix writing loop.

Useful flags: `--vendor SLUG`, `--all`, `--batch`, `--stage NAME` (repeatable), `--date YYYY-MM-DD`, `--list-stages`, `--force`.

## Requirements

- Python 3.10 or newer (3.11 and 3.13 are tested in CI)
- Poppler on PATH (`pdftohtml`, `pdftoppm`, `pdfimages`, `pdftotext`) for extract
- Tesseract on PATH (`tesseract`, English data) for image OCR on the technical path
- An owner exam sheet (`catalog.csv` or a sheet for the catalog stage) and owner question PDFs
- Official vendor URLs for part 2 (saved copies are reused; `--offline` never fetches)

## Install

Pick one of the methods below. After any of them, `certpassly-pipeline --help` should work. On Windows, prefer PowerShell and `install.ps1`. Git Bash can also run `install.sh`.

### Tools on Linux

```bash
sudo apt-get update
sudo apt-get install -y poppler-utils tesseract-ocr tesseract-ocr-eng
```

### Tools on Windows (PowerShell)

A common option is Chocolatey, which is also what CI uses:

```powershell
choco install poppler tesseract -y
```

Add Tesseract to PATH, or set `TESSERACT_DIR` to the folder that contains `tesseract.exe` and restart the shell:

```powershell
# default install location for the UB Mannheim and Chocolatey packages
$env:TESSERACT_DIR = "C:\Program Files\Tesseract-OCR"
# persist for new shells if you need it:
# [Environment]::SetEnvironmentVariable("TESSERACT_DIR", "C:\Program Files\Tesseract-OCR", "User")
```

The scripts also look in `C:\Program Files\Tesseract-OCR` and `C:\Program Files (x86)\Tesseract-OCR` when `tesseract` is not already on PATH. You can install Tesseract from the [UB Mannheim installer](https://github.com/UB-Mannheim/tesseract/wiki) instead of Chocolatey. Add Poppler's `Library\bin` folder to PATH so `pdftohtml` is found, then restart PowerShell.

### From Git or a local clone

```bash
git clone https://github.com/msaqlainhaneef1/certpassly-exam-pipeline.git
cd certpassly-exam-pipeline
git checkout v1.3.0
python -m venv .venv
```

Linux or macOS:

```bash
source .venv/bin/activate
pip install -e .
# optional, only for JavaScript official pages in part 2:
# pip install -e ".[render]"
# python -m playwright install chromium
certpassly-pipeline --help
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
# or: Set-ExecutionPolicy -Scope Process Bypass; .\install.ps1
pip install -e .
certpassly-pipeline --help
```

`./install.sh` and `.\install.ps1` create `.venv`, install the package in editable mode, check for poppler and tesseract, and run the unit tests.

A non-editable `pip install .` is enough for `--help`. Full runs need a clone (`pip install -e .`) or `CERTPASSLY_SKILL_ROOT` so `SKILL.md`, `reference/`, `config/` and `shared/` resolve.

You can also install from the Git URL for `--help`:

```bash
pip install "git+https://github.com/msaqlainhaneef1/certpassly-exam-pipeline.git"
```

A non-editable `pip install git+...` puts the code in site-packages and does not ship `reference/` next to the module unless you set `CERTPASSLY_SKILL_ROOT` to a clone of this repo.

### From a zip

Copy the zip to a folder you control (on Windows, the Desktop is a reliable place; a zip opened from a chat window may not extract). Unzip it, then run `./install.sh` or `.\install.ps1` as above.

### Environment

Copy `.env.example` and export any values you need. The scripts read process environment variables; they do not load a `.env` file by themselves. Never commit real keys.

## Quick start (part 1)

```bash
cp config/pipeline.example.yaml /path/to/workspace/config/pipeline.yaml
cp config/vendors.example.yaml /path/to/workspace/config/vendors.yaml
# add catalog.csv (or run the catalog stage from the owner sheet)
# put the owner PDFs in owner-files/EXAM-CODE/
# set owner_rights_statement in pipeline.yaml
certpassly-pipeline --exam EXAM-CODE --root /path/to/workspace --offline
```

Windows PowerShell is the same, with Windows paths in quotes:

```powershell
certpassly-pipeline --exam EXAM-CODE --root "C:\path\to\workspace" --offline
```

The export runs a config-driven fidelity gate. A question is written to the site file only when coverage, OCR, type and key checks all pass. Held items go to `export/cannot-convert.json` and are listed in `export/fidelity.md`. See [docs/fidelity.md](docs/fidelity.md).

To also run the site PHP schema checker, set `CERTPASSLY_SITE_VALIDATOR` to the site file `app/Support/SiteFormat/SchemaValidator.php` (read only) and have `php` on PATH.

## Site schema (v2)

The technical export writes one site v2 exam file: `out/EXAM-CODE/EXAM-CODE.site-format.v2.json`.

`reference/site-format/v2/question.schema.json` is a verbatim copy of the site schema from worktree commit `a3009daa5` (full hash `a3009daa5758a4401ceadd9cf765d8a36bff22bc`). The schema file sha256 is `da9331c562a0e08cd156cc5efe6181cb8910ec19c523ff83dc43687190dc728e`. Provenance is in `reference/site-format/v2/PROVENANCE.md`. Do not edit the schema by hand.

To refresh the copy when the site schema changes:

1. From a read-only site worktree, copy `reference/site-format/v2/question.schema.json` over the same path in this repo.
2. Record the new site commit and `sha256sum` (or `Get-FileHash -Algorithm SHA256` on Windows) in `PROVENANCE.md`.
3. Run `python scripts/validate_question_v2.py --examples reference/site-format/v2/examples` and the unit tests.
4. If the site `SchemaValidator.php` class also changed, point `CERTPASSLY_SITE_VALIDATOR` at the new class file (still read only) and re-run `validate_site`.

This skill does not change site code or the database.

## Stages, inputs and outputs

Technical default (part 1):

| Stage | Inputs | Outputs |
| --- | --- | --- |
| intake | `owner-files/<CODE>/` (or Drive when online) | `out/<CODE>/intake/files.json`, `rights-confirmation.md` |
| extract | The owner PDF, `config/ocr.json` | `extracted/` (`raw.xml`, `split.json`, `items/`, `ocr.json`, `visual_draft.json`, `layout.json`, `cleanups.json`, `unparsed.json`), `media/src/` |
| export | Extract, `catalog.csv`, `config/question_type_rules.json`, `config/fidelity.json` | `<CODE>.site-format.v2.json`, `questions.json`, `export/technical_report.json`, `export/cannot-convert.json`, `export/fidelity.json`, `export/fidelity.md` |
| validate_site | The site v2 file, the copied schema, optional site PHP checker | Pass or fail on every exported question |
| package | `out/<CODE>/` (vendor and cert pages only if research JSON exists) | `<CODE>-package.zip`, after the package guard drops raw extracts and scans the zip against the denylist |

Part 2 stages (research and verify) still use `catalog.csv`, saved official sources, `research/` (including search-intent and optional competitor-notes), `authoring/`, pages, import CSVs, `questions.json`, `validate.py`, `check_bank.py`, the writing check and the package guard. See `certpassly-pipeline --list-stages`, [docs/AI-OPERATOR-GUIDE.md](docs/AI-OPERATOR-GUIDE.md) and [HANDOVER.md](HANDOVER.md).

## Run folder layout

```
WORKSPACE/
  catalog.csv
  config/pipeline.yaml
  config/vendors.yaml
  owner-files/EXAM-CODE/*.pdf
  out/EXAM-CODE/
    intake/files.json
    extracted/          # split, OCR, visual draft, raw XML
    media/src/          # images from the PDF
    export/             # technical_report, cannot-convert, fidelity
    EXAM-CODE.site-format.v2.json
    questions.json
  EXAM-CODE-package.zip
  run.log
```

`--root` is the workspace, not the skill repo.

## Fidelity gate

Export is strict and config-driven. Defaults live in `config/fidelity.json` (OCR pass settings are also under `config/ocr.json` in the `fidelity` block). Nothing is hardcoded per exam.

A question is exported only when all of these pass:

1. Word coverage of the scrubbed PDF text and high-confidence image OCR words is 100 percent, and the export adds no extra words.
2. Each OCR'd image is run twice. Every word is at or above 90 confidence, overall confidence is at least 95, and both passes agree on the text.
3. Exactly one type rule matches, and the interaction shape agrees with the answer key.
4. The answer key comes from the text layer, or from a pixel mark that passes two methods, and it maps to existing ids. The key is never inferred.

Tune thresholds only in those config files, and only in the safer direction unless you have a reason. Lowering confidence, turning off pass agreement, or allowing an uncertain key will export items that are not confirmed. See [docs/fidelity.md](docs/fidelity.md) for hold reasons and what to do for each.

## Adding a vendor or a type rule

Do not hardcode an exam code or a vendor name in shared scripts.

- New vendor: add a slug in `config/vendors.yaml`. Use the `generic` adapter, or add a module under `scripts/adapters/` if the official pages need their own parser. Seed URL patterns and `render` flags go in that vendor entry, not in exam-specific branches.
- New exam: add a row to `catalog.csv` (or the owner sheet) with vendor, certification, exam code and exam name. Put PDFs in `owner-files/<CODE>/`.
- New question type rule: add a mutually exclusive rule to `config/question_type_rules.json`. Use `all`, `any`, `none` and `not_all`. The type must already exist in the site registry. See [docs/question-type-rules.md](docs/question-type-rules.md).

## How to read held items

Open `out/<CODE>/export/fidelity.md` (one line per question) and `export/cannot-convert.json` (the hold reason). Exported questions should all show 100 percent coverage.

| Hold kind | What it means | What to do |
| --- | --- | --- |
| Owner key conflict | The stem asks for N choices but the PDF key has a different count, or a cloze/matrix shape does not match the key | Do not infer the missing letters. Review the PDF `Correct Answer` line with the owner. |
| Low OCR | A word is below 90 or overall confidence is below 95 | Keep the item held. A later pass can raise page render resolution. Do not type the words in by hand as a guess. |
| Dual OCR disagreement | The two OCR passes did not agree on the text | Same as low OCR: improve the image or the render, then re-run extract. |
| Pixel key not certain | Visual marks did not agree on two methods, or no text key maps to existing ids | Do not infer a key. Ask the owner to confirm the mark, or supply a clearer answer image. |
| Type ambiguous | Zero rules or more than one rule matched | Adjust a general rule in `config/question_type_rules.json`, or leave the item held for the owner. Never guess the type. |

## Real test results (15 Nov 2026, Asia/Karachi)

Four owner PDFs were run through part 1 into fresh folders under `/workspace/runs/fid-1115`. Scripts only. Every exported question had 100 percent word coverage. Python and site PHP validators passed on every exported question.

| Exam | Expected | Extracted | Exported | Held | Exported types | Validators |
| --- | --- | ---: | ---: | ---: | --- | --- |
| AB-730 | 92 | 92 | 48 | 44 | 37 single_choice, 11 multiple_select | 48/48 both |
| 4A0-AI1 | 80 | 80 | 75 | 5 | 75 single_choice | 75/75 both |
| ADM-201 | 234 | 234 | 231 | 3 | 165 single_choice, 66 multiple_select | 231/231 both |
| KCNA | 300 | 300 | 299 | 1 | 299 single_choice | 299/299 both |

None of the four exams is 100 percent complete. KCNA is closest (299/300). What blocks the rest: AB-730 visual items fail OCR confidence, dual-pass agreement or two-method pixel keys; 4A0-AI1 holds five code or exhibit images for the same OCR rules; ADM-201 and KCNA hold items where the stem asks for more than one choice but the owner PDF key is a single letter; ADM-201 has no catalog row, so the header vendor is `Vendor`.

## Push flow, CI and branch rules

The box cannot push to GitHub. The owner's Windows PC can (`gh` as `msaqlainhaneef1`). The safe path is a git bundle.

On the box, the 1.3.0 release bundle is built from `main` at `13dea6b` (the GitHub main tip this release fast-forwards) and includes `main`, `feat/question-format-v2`, `release/v1.3.0` and tag `v1.3.0`:

```bash
git bundle create /workspace/deliverables/question-v2/release-v1.3.0.bundle ^13dea6b main feat/question-format-v2 release/v1.3.0 v1.3.0
```

The exact command used for this release is recorded in HANDOVER.md. Copy the bundle to the PC, then fetch `main`, `feat/question-format-v2`, `release/v1.3.0` and tag `v1.3.0`. `main` is a fast-forward from `13dea6b`. Push `main` and tag `v1.3.0`. Do not force-push. Do not rewrite the existing `v1.2.0` tag on GitHub (that tag is the 11 Nov 2026 writing-brief release at `6223659`).

CI (`.github/workflows/tests.yml`) runs on pushes to `main` and `feat/**`, and on pull requests. The matrix is Ubuntu and Windows, Python 3.11 and 3.13 (four jobs). All must pass.

## Known gaps and next improvements

Ranked, most useful first:

1. Add an ADM-201 row to `catalog.csv` (the sheet today lists Plat-Admn-201). Do not invent a vendor or map the codes in a script.
2. Ask the site team to add official vendor hosts to `SITE_FORMAT_LINK_DOMAINS` so kept official links import cleanly.
3. Use higher resolution page renders for OCR, so more visual items can pass the 90/95 and dual-pass checks.
4. Give the owner a review sheet of held items (key from `fidelity.md` and `cannot-convert.json`) so conflicts can be resolved without guessing.
5. Take question domains from the catalog (or official outline) instead of the `Unassigned` fallback.

## What this skill does not do

- It does not invent questions. Questions come only from owner PDFs.
- It does not merge or guess question types.
- It does not infer an answer key.
- It does not publish. Pages and exam files stay draft.
- It does not change site code or the database.
- It does not trust cover-page exam facts in an owner file when they disagree with the official page.

## Layout

- `SKILL.md` / `SKILL_BODY.md` / `DESCRIPTION.txt`: skill entry and a frontmatter-free body
- `README.md`, `HANDOVER.md`, `CHANGELOG.md`, `AGENTS.md`, `docs/`: how to run and reuse the pipeline (operator guide and training exercises live under `docs/`)
- `scripts/`: pipeline (packaged as `certpassly_pipeline`)
- `scripts/adapters/`: official-source parsers (generic plus per-vendor modules)
- `config/`: pipeline, vendors, type rules, OCR and fidelity
- `reference/`: rules, lessons, site-format snapshots
- `shared/`: reusable content blocks
- `tests/`: offline regression and dry run
- `install.sh`, `install.ps1`, `pyproject.toml`, `requirements.txt`

## Tests

```bash
python -m unittest discover -s tests -v
```

On Windows PowerShell:

```powershell
python -m unittest discover -s tests -v
```

CI runs the same command on Linux and Windows with 0 skipped tests. `tests/test_fidelity.py` and `tests/test_technical_path.py` cover the technical path. `tests/test_docs.py` checks these docs for typographic dashes and emoji. `tests/test_ai_guide.py` checks that the operator guide, training exercises, AGENTS.md and HANDOVER.md match the stage list and real flags.

`tests/test_demo_end_to_end.py` builds two synthetic demo exams (Microsoft adapter and generic adapter) with `tests/demo_kit.py` and runs `research` then `verify`. `tests/test_v120.py` covers the writing brief, the banned AI-phrase list, search intent, competitor notes as topics only, and the check-then-fix loop. Try a technical demo with `python tests/demo_kit.py microsoft DEMO_DIR` then `certpassly-pipeline --exam DM-101 --root DEMO_DIR --offline --date 2026-11-11`. For part 2, run `research` then `verify` on the same demo.

To check produced import files against `reference/site-format/v1` (CSV headers, allowed statuses, simulator schema, including researched and answer_not_found fields):

```bash
python scripts/check_import_conformance.py --root /path/to/workspace --exam EXAM-CODE
# or: python scripts/check_import_conformance.py --package EXAM-package.zip
```

This is not a live run of the site importer.

The gold-package regression runs only when `CERTPASSLY_GOLD` points at a local gold workspace. Real owner extracts are never committed.

## License

Proprietary. For use by CertPassly.
