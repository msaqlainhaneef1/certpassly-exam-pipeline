# CertPassly exam pipeline

A scripts-first skill that turns official vendor pages and owner question PDFs into draft, site-ready exam pages and question-import files for CertPassly.

The pipeline does not read the CertPassly application repository, run artisan, or call GitHub. Site contracts (question types, CSV layouts, URL rules, allowed statuses, page fields) live in a versioned snapshot at `reference/site-format/v1/`.

The only AI stage is `author` (batched). Everything else is scripted.

Read [reference/lessons-learned.md](reference/lessons-learned.md) before you run a new exam. The same top rules are repeated in `SKILL.md`.

## Requirements

- Python 3.10 or newer
- [poppler](https://poppler.freedesktop.org/) on PATH (`pdftohtml`, `pdftoppm`, `pdftotext`) for the extract stage
- [Tesseract](https://github.com/tesseract-ocr/tesseract) on PATH, optional, for image-only questions
- An owner exam sheet (CSV) and owner question PDFs
- Official vendor URLs (saved copies are reused; `--offline` never fetches)

## Install

Pick one of the three methods. After any of them, `certpassly-pipeline --help` should work.

On Windows, prefer PowerShell and `install.ps1`. Git Bash can also run `install.sh`.

### From Git

Once this repository has a remote (the maintainer will tell you which one):

```bash
git clone https://github.com/<owner>/<repo>.git
cd <repo>
# Linux / macOS / Git Bash
./install.sh
# Windows PowerShell
#   Set-ExecutionPolicy -Scope Process Bypass
#   .\install.ps1
```

Or install the package directly from the Git URL (no local clone of the docs needed for `--help`):

```bash
python -m venv .venv
# Linux / macOS:  source .venv/bin/activate
# Windows PowerShell:  .\.venv\Scripts\Activate.ps1
pip install "git+https://github.com/<owner>/<repo>.git"
certpassly-pipeline --help
```

Optional, for JavaScript-built official pages (Salesforce exam guides, for example):

```bash
pip install -e ".[render]"
python -m playwright install chromium
```

A non-editable `pip install git+...` puts the code in site-packages and does not ship `reference/` next to the module unless you set `CERTPASSLY_SKILL_ROOT` to a clone of this repo. For a full pipeline run, use `pip install -e .` inside a clone, or set that variable.

### From a local clone, with pip

```bash
git clone https://github.com/<owner>/<repo>.git
cd <repo>
python -m venv .venv
# Linux / macOS:  source .venv/bin/activate
# Windows PowerShell:  .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
certpassly-pipeline --help
```

`pip install .` (non-editable) is supported and is verified for `--help`. Use `pip install -e .` when you will run stages, so `SKILL.md`, `reference/`, `config/` and `shared/` resolve automatically.

### From a zip

Copy the zip to a folder you control (on Windows, the Desktop is a reliable place; a zip opened from a chat window may not extract). Unzip it, then:

```bash
cd certpassly-exam-pipeline
# Linux / macOS / Git Bash
./install.sh
# Windows PowerShell
#   Set-ExecutionPolicy -Scope Process Bypass
#   .\install.ps1
```

The install scripts create `.venv`, install the package in editable mode, check for poppler and tesseract, and run the unit tests.

### Environment

Copy `.env.example` and export any values you need. The scripts read process environment variables; they do not load a `.env` file by themselves. Never commit real keys.

## Quick start

```bash
cp config/pipeline.example.yaml /path/to/workspace/config/pipeline.yaml
cp config/vendors.example.yaml /path/to/workspace/config/vendors.yaml
# add catalog.csv (or run the catalog stage from the owner sheet)
# put the owner files in owner-files/EXAM-CODE/ and set owner_rights_statement in pipeline.yaml
certpassly-pipeline --exam EXAM-CODE --root /path/to/workspace --offline
```

Useful flags: `--vendor SLUG`, `--all`, `--batch`, `--stage NAME` (repeatable), `--date YYYY-MM-DD`, `--list-stages`, `--force`.

Default stages: catalog, intake, sources, research, extract, author, pages, import, bank, validate, package.

Vendor and certification pages are built once and reused when their inputs have not changed.

## What this skill does not do

- It does not invent questions. Questions come only from owner PDFs.
- It does not merge question types. The 30 types in site-format stay distinct.
- It does not publish. Pages are written as draft. A human still has to pass the publish gates.
- It does not change site code or the database.
- It does not trust cover-page exam facts in an owner file when they disagree with the official page.

## Layout

- `SKILL.md` / `SKILL_BODY.md` / `DESCRIPTION.txt` : skill entry and a frontmatter-free body
- `scripts/` : pipeline (packaged as `certpassly_pipeline`)
- `scripts/adapters/` : official-source parsers (generic plus per-vendor modules)
- `config/` : example pipeline and vendor registry
- `reference/` : rules, lessons, site-format snapshot
- `shared/` : reusable content blocks
- `tests/` : offline regression and dry run
- `install.sh`, `install.ps1`, `pyproject.toml`, `requirements.txt`

## Tests

```bash
python -m unittest discover -s tests -v
```

To check produced import files against `reference/site-format/v1` (CSV headers, allowed statuses, simulator schema, including researched and answer_not_found fields):

```bash
python scripts/check_import_conformance.py --root /path/to/workspace --exam EXAM-CODE
# or: python scripts/check_import_conformance.py --package EXAM-package.zip
```

This is not a live run of the site importer.

`tests/test_demo_end_to_end.py` builds two synthetic demo exams (Microsoft adapter and generic adapter) with `tests/demo_kit.py` and runs every stage through the CLI. Try it: `python tests/demo_kit.py microsoft /tmp/demo` then `certpassly-pipeline --exam DM-101 --root /tmp/demo --offline --date 2026-11-11`.

The gold-package regression rebuilds a finished real exam from a cached workspace. It runs only when `CERTPASSLY_GOLD` points at that workspace and is not collected otherwise, so CI shows 0 skipped. That workspace is not committed (see `tests/fixtures/README.md`).

## License

Proprietary. For use by CertPassly.
