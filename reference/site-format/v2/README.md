# Site format v2

Question format v2 is an extension of the site Universal Question Engine (UQE). It is not a rewrite of the website. v1 in this folder is unchanged and remains the workbook and type snapshot the current pipeline uses.

v2 adds a formal JSON Schema (Draft 2020-12) for one question, a sanitizer allow-list, reveal rules, and an image-question guide. Files only. This skill does not change site worktree code, production, or the database.

`schema_version` is the const `question.v2`. The 30 type keys are parsed from the site `config/question_types.php`. Every question, including items that started as images, must be a real v2 HTML or SVG type. Images are supporting media only, with alt text, and are never the question itself. There is no `image_legacy` type. Do not map old image questions to `image_based_choice` as a shortcut. `registry-mismatch.json` has zero mismatches. Canonical `answer_key_status` is `owner_key`. The v1 spelling `as_in_source_file` is not valid in v2; `scripts/migrate_v1_to_v2.py` maps v1 statuses and items. The schema and the validator reject that alias. Free-trial caps live in site entitlements. This schema has no trial fields.

## File map

- `question.schema.json`: author and import document. Stable `question_key` plus integer `version`. Learner block and answer block are separate. Partial credit is per type. `scoring_excluded` must be true when `answer_key_status` is `answer_not_found`.
- `question_types.json`: script output of the 30 PHP types, aliases, and publishable / staging / blocked lists.
- `registry-mismatch.json`: requested types that are not in the PHP file. This file has zero mismatches. The enum is exactly the 30 PHP keys.
- `sanitizer-allowlist.json`: allowed HTML and SVG, forbidden elements, and differences from `SecurityHardeningService::sanitizeSvgContent`.
- `reveal-rules.md`: learner versus answer, practice versus exam, offline rule 143, free trial rule 216, rule 21, and the three known site key-leak bugs.
- `image-questions.md`: tables, text, and choices become HTML; diagrams become exact SVG; photos and UI shots stay supporting media; original file always kept; inexact items go on the cannot-convert list.
- `examples/`: valid examples for core types (including a `single_choice` item with a supporting image) and two invalid examples.
- `scripts/parse_question_types_php.py`, `scripts/validate_question_v2.py`, `scripts/export_question_v2.py`, and `scripts/migrate_v1_to_v2.py` live in the skill `scripts/` folder.

## Commands

Parse the site registry (read-only PHP path):

```
python scripts/parse_question_types_php.py /path/to/config/question_types.php \
  -o reference/site-format/v2/question_types.json \
  --mismatch-out reference/site-format/v2/registry-mismatch.json
```

Validate the bundled examples:

```
python scripts/validate_question_v2.py --examples reference/site-format/v2/examples
```

Valid examples must pass. Invalid examples must fail.

Migrate a v1 bank to v2 drafts (maps statuses, transcribes image items to HTML or SVG types, and writes the cannot-convert report). Do not use `export_question_v2.py` on a raw v1 bank:

```
python scripts/migrate_v1_to_v2.py \
  --bank /workspace/runs/dc101/out/Data-Con-101/questions.json \
  --out /workspace/deliverables/question-v2/migrated/Data-Con-101 \
  --cannot-convert /workspace/deliverables/question-v2/cannot-convert

python scripts/validate_question_v2.py --dir /workspace/deliverables/question-v2/migrated/Data-Con-101
```

Run unit tests:

```
python -m unittest tests.test_question_v2 -v
```

## How this fits the site importer

- Imports stay drafts. The site importer must still quarantine unknown or disabled types and must not coerce them to MCQ.
- Map `learner` into `public_view` / `stimulus` / `response_schema`. Map `answer.answer_key` into encrypted `question_answer_keys`. Never write the answer block into a candidate payload.
- `max_choices` and `choose_n` come from the authored learner constraints.
- `answer_key_status` values in v2 are `owner_key`, `researched_official`, `researched_unverified`, and `answer_not_found`. The v1 spelling `as_in_source_file` is rejected. Run `scripts/migrate_v1_to_v2.py` to map a v1 bank (it may record the original spelling in `meta.legacy_answer_key_status`). The live site importer still needs to accept the researched and `answer_not_found` fields (open item from v1.1.0).
- Free-trial caps (owner rule 216: 1 week, 10 questions, 2 simulator uses) live in site entitlements, not in question JSON. This schema has no trial fields.
- Re-import key: `question_key` + integer `version`. Same key and a new version updates. It must not insert a second row with the same key.
- Run `sanitizeSvgContent` (and an HTML sanitizer) on the server at ingest, even when this schema already passed.
- Do not deploy v2 items to production until the three reveal bugs in `reveal-rules.md` are fixed and the owner has approved tests.

## Drafts only

Every example and every migrated export uses `meta.record_status: "draft"` and `meta.verification_status: "unverified"`. This pipeline does not mark records verified, reviewed, approved, published, or active.
