# Site format v2

Question format v2 is an extension of the site Universal Question Engine (UQE). It is not a rewrite of the website. v1 in this folder is unchanged and remains the workbook and type snapshot the current pipeline uses.

v2 adds a formal JSON Schema (Draft 2020-12) for one question, a sanitizer allow-list, reveal rules, and an image-question guide. Files only. This skill does not change site worktree code, production, or the database.

`schema_version` is the const `question.v2`. The 30 type keys are parsed from the site `config/question_types.php`. `image_legacy` was requested for compatibility and is flagged in `registry-mismatch.json` because it is not in that registry. It was not added to the enum.

## File map

- `question.schema.json`: author and import document. Stable `question_key` plus integer `version`. Learner block and answer block are separate. Partial credit is per type. `scoring_excluded` must be true when `answer_key_status` is `answer_not_found`.
- `question_types.json`: script output of the 30 PHP types, aliases, and publishable / staging / blocked lists.
- `registry-mismatch.json`: requested types that are not in the PHP file.
- `sanitizer-allowlist.json`: allowed HTML and SVG, forbidden elements, and differences from `SecurityHardeningService::sanitizeSvgContent`.
- `reveal-rules.md`: learner versus answer, practice versus exam, offline rule 143, free trial rule 216, rule 21, and the three known site key-leak bugs.
- `image-questions.md`: tables and text to HTML, exact diagrams to SVG, photos and UI shots as images, original file always kept.
- `examples/`: valid examples for core types, one `image_legacy` mismatch example, and two invalid examples.
- `scripts/parse_question_types_php.py`, `scripts/validate_question_v2.py`, `scripts/export_question_v2.py` live in the skill `scripts/` folder.

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

Valid examples must pass. Invalid examples and the `image_legacy` mismatch must fail.

Export a draft bank (example: Data-Con-101) and validate the pilot:

```
python scripts/export_question_v2.py \
  --bank /workspace/runs/dc101/out/Data-Con-101/questions.json \
  --out /workspace/deliverables/question-v2/pilot/Data-Con-101

python scripts/validate_question_v2.py --dir /workspace/deliverables/question-v2/pilot/Data-Con-101
```

Run unit tests:

```
python -m unittest tests.test_question_v2 -v
```

## How this fits the site importer

- Imports stay drafts. The site importer must still quarantine unknown or disabled types and must not coerce them to MCQ.
- Map `learner` into `public_view` / `stimulus` / `response_schema`. Map `answer.answer_key` into encrypted `question_answer_keys`. Never write the answer block into a candidate payload.
- `max_choices` and `choose_n` come from the authored learner constraints.
- `answer_key_status` values in v2 are `owner_key`, `researched_official`, `researched_unverified`, and `answer_not_found`. The exporter maps v1 `as_in_source_file` to `owner_key` and keeps the old value in `meta.legacy_answer_key_status`. The live site importer still needs to accept the researched and `answer_not_found` fields (open item from v1.1.0).
- Re-import key: `question_key` + integer `version`. Same key and a new version updates. It must not insert a second row with the same key.
- Run `sanitizeSvgContent` (and an HTML sanitizer) on the server at ingest, even when this schema already passed.
- Do not deploy v2 items to production until the three reveal bugs in `reveal-rules.md` are fixed and the owner has approved tests.

## Drafts only

Every example and every pilot export uses `meta.record_status: "draft"` and `meta.verification_status: "unverified"`. This pipeline does not mark records verified, reviewed, approved, published, or active.
