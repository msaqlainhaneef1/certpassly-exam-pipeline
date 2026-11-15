# Question type rules

File: `config/question_type_rules.json`.

The technical export classifies each question from this table. Rules are general. Do not put an exam code, a vendor name, or a one-off exception in this file or in `scripts/qtypes.py`.

The type value must already exist in the site registry (`reference/site-format/v2/question_types.json`, parsed from the site list of 30 types).

## How a rule matches

Each rule has an `id`, a `type`, a `reason`, and conditions:

- `all`: every condition in the list must be true
- `any`: at least one condition in the list must be true
- `none`: none of these conditions may be true
- `not_all`: a group of conditions that must not all be true together (for example, exhibit wording plus a question image, which belongs to `image_based_choice` instead of `single_choice`)

The fidelity gate exports a question only when exactly one rule matches, and when the interaction shape agrees with the answer key (matrix rows equal key rows, choose N wording equals the key count, every cloze blank has a key). If zero or more than one rule matches, the item is held. The type is never guessed.

`classify_detailed` still records every match. The first match can supply a type for the older bank path. The technical export does not use a first-match guess when matches are not unique.

## Common conditions

Examples: `has_options`, `option_count` / `option_count_min` / `option_count_max`, `option_texts_in` / `option_texts_not_in`, `marker` / `markers_any` / `markers_all`, `not_marker` / `not_markers_any`, `has_question_image`, `answer_letter_count` / `_min` / `_max`, `visual_rows_min`, `visual_blanks` / `visual_blanks_min`, `visual_type`, `visual_has`, `visual_regions_min`, `answer_region_count_min`.

Markers (yes_no, dropdown, multi, exhibit, hotspot, dragdrop) are patterns in the same file, applied to the stem.

## How to add a rule

1. Confirm the site type key already exists. Do not invent a type.
2. Add a new object to the `rules` list with a unique `id`.
3. Write `all` / `any` / `none` / `not_all` so the rule cannot also match an existing rule (for example `single_choice` must not also match `true_false` or `multiple_select`).
4. Add a unit test in `tests/test_technical_path.py` or `tests/test_fidelity.py` that the new shape matches exactly one rule.
5. Run `python -m unittest discover -s tests -v`.

If a real PDF item is held as type ambiguous, fix a general condition. Do not add an exam-specific rule.

## Domain fallback

`default_domain` (currently `Unassigned`) is used when the catalog does not supply a domain. A later improvement is to take domains from the catalog or the official outline instead.
