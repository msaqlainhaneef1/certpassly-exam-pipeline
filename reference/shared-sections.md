# Shared sections

Reusable blocks, written once and reused. This saves author-stage work and keeps policy wording consistent.

## Levels

- `site` : simulator / practice how-it-works, scoring, study method, exam-day checklist, independence disclaimer, editorial / update policy
- `vendor` : booking through the official delivery partner, vendor account, retake, identification rules
- `certification` : renewal, path, related credentials
- `question-type` : how to answer each of the 30 types in site-format

## Storage

```
shared/<level>/<slug-or-key>.json
  site/<key>.json
  vendor/<vendor-slug>/<key>.json
  certification/<cert-slug>/<key>.json
  question-type/<type-key>.json
```

Each file has `version`, `sources`, `last_updated`, `title` and `body_html` (or `body`). Workspace copies under `--root/shared/` override the skill seeds.

This skill ships site-wide seeds, question-type how-tos, and a first vendor-level set under `shared/vendor/` taken from the first finished exam package (booking, retake, identification, account). Add other vendors the same way.

## Insert

In `page_prose.json`, either:

- put a marker in `body_html`: `{{shared:site:study-method}}` or `{{shared:vendor:booking}}` (the vendor slug comes from the exam context), or
- list `shared_keys: [{level, key, slug?}, ...]` on that page record. Missing keys are appended.

`build_pages.py` inserts by key. The author stage writes a block only when it does not already exist (`shared_sections.list_missing`). Cached full `body_html` without markers is left unchanged, so a frozen package can still match byte-for-byte.

## Limits (enforced)

- A page body may not take more than `shared_max_share` of its wording from shared blocks (default 0.4, set in `pipeline.yaml`). Measured as 5-word shingle overlap in `validate.py` check 18.
- Shared blocks go through the same banned-term, contact-pattern and typographic-dash gates as pages (check 18b).
- Duplicate-content checks across generated pages still apply.

Shared text is a starting layer, not the whole page. Exam-specific facts, official quotes and original prose still have to be written for that exam.
