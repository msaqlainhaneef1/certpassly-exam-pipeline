# Site format v2

This folder holds the CertPassly site format v2 used for exam and question import JSON. v1 in the parent folder is unchanged and remains the workbook and type snapshot the current pipeline uses for catalog pages.

`question.schema.json` is a verbatim copy of the site schema. See `PROVENANCE.md` for the site commit and sha256. The earlier pipeline-only schema (one file per question, with `schema_version`, `meta` and `constraints`) is retired under `retired/` and is not used.

The document is one file per exam. An `exam` object (vendor, certification, exam code, name, optional duration, passing score, question count, domains, last vendor update, simulator settings) sits on top, and every question lives in `questions`. Each question has `question_key`, integer `version`, `type`, `domain`, a `learner` block and an `answer` block. No raw HTML or SVG is allowed. Text is rich_text (paragraphs and lists, with bold, italic, code and https links). Tables, diagrams, code samples, exhibits and case studies use `content_blocks`. Images are supporting media only, with an https or `/storage/` URL and plain-text alt text.

Canonical `answer.status` values are `owner_key`, `researched_official`, `researched_unverified` and `answer_not_found`. The v1 spelling `as_in_source_file` is not valid. `scripts/migrate_v1_to_v2.py` maps v1 statuses and items. `scoring_excluded` must be true when status is `answer_not_found`. Free-trial caps live in site entitlements. `counts_toward_trial` is an exam simulator setting, not a per-question field.

## File map

- `question.schema.json`: the site schema (the single rule book).
- `PROVENANCE.md`: where the schema was copied from, and its sha256.
- `question_types.json`: script output of the 30 PHP types, aliases, and publishable / staging / blocked lists.
- `registry-mismatch.json`: requested types that are not in the PHP file. This file has zero mismatches.
- `sanitizer-allowlist.json`: kept for history. The site format itself forbids raw HTML and SVG.
- `reveal-rules.md`: learner versus answer, practice versus exam, and known site reveal bugs.
- `image-questions.md`: how image items are handled; inexact items go on the cannot-convert list.
- `examples/`: valid exam files for core types and two invalid files.
- `scripts/validate_question_v2.py`, `scripts/export_question_v2.py`, `scripts/migrate_v1_to_v2.py` and `scripts/validate_site_schema.php` live in the skill `scripts/` folder.

## Commands

```
python scripts/validate_question_v2.py --examples reference/site-format/v2/examples

python scripts/migrate_v1_to_v2.py \
  --exam-dir /path/to/exam-output \
  --out /path/to/out \
  --cannot-convert /path/to/cannot-convert

python scripts/validate_question_v2.py --dir /path/to/out

php scripts/validate_site_schema.php \
  --schema reference/site-format/v2/question.schema.json \
  --validator /path/to/site/app/Support/SiteFormat/SchemaValidator.php \
  /path/to/out/EXAM.site-format.v2.json
```

Do not run `export_question_v2.py` on a raw v1 bank. Use the migrator first.

## How this fits the site importer

- The site only serves v2 when `SITE_FORMAT_EXAM_V2` is on (off by default).
- Links in text and `answer.references` must use a host in `SITE_FORMAT_LINK_DOMAINS` (the site host by default). Official vendor links are kept in the export and counted; the site team needs to allow those domains before import will accept them.
- The importer also checks duplicate question text (warn by default) and repeated ids. The pipeline checks both first.
- Imports stay drafts. Types without a component are held. Domain names on questions must exist on the exam.
- Re-import key: `question_key` plus integer `version`.
- Do not deploy v2 items to production until the owner has approved tests. This skill does not change site worktree code, production, or the database.

## Drafts only

Every example and every migrated export is a draft import file. This pipeline does not mark records verified, reviewed, approved, published, or active.
