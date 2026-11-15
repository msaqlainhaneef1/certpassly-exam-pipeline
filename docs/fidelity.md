# Fidelity gate

File: `config/fidelity.json`. Thresholds are also mirrored under `config/ocr.json` in the `fidelity` block. Nothing in these files is hardcoded per exam.

The technical export (`scripts/build_technical_export.py` and `scripts/fidelity.py`) runs this gate on every question. The item is written to the site v2 file only when every check passes. Otherwise it is held in `export/cannot-convert.json` and listed in `export/fidelity.json` and `export/fidelity.md`.

## The checks

1. Word coverage, using the PDF text. The source block is the question stem, choices, answer area and exhibit text, minus only the brand and boilerplate denylist and the `Correct Answer` / `Section` / `Explanation` labels (line patterns, not mid-stem words such as "reference"). Those words are compared with all text in the exported question (stem, choices, content blocks, matrix rows and columns, cloze segments and blanks, image alt). Export only if coverage is 100 percent and no extra words appear. Invented alt text is not allowed; alt must come from OCR words.
2. Word coverage, using the images. Each OCR'd image must have every word at or above 90 confidence (configurable) and overall confidence of at least 95. OCR runs twice (two `psm` or preprocess settings). Both results must agree on the text. Otherwise the question is held, with the low words or the disagreement in the reason.
3. Type certainty. Exactly one type rule must match, and the interaction shape must agree with the answer key (matrix rows equal key rows, choose N wording equals the key count, every cloze blank has a key). Zero or more than one rule: hold.
4. Answer key certainty. The key must come from the text layer (`answer_raw` / Correct Answer) or from a pixel mark that passes two methods (`marker_box`, `highlight`, `checked_box`), and it must map to existing choice, row or blank ids. The key is never inferred. Items with no certain key are held.
5. Site format. Python `scripts/validate_question_v2.py` and, when configured, the site PHP `SchemaValidator` run on 100 percent of the exported questions.

## How to read the report

`export/fidelity.md` has one line per question: exported or held, coverage percent, OCR minimum word confidence, type rule, key source and reason. `export/fidelity.json` is the same data as JSON. `export/cannot-convert.json` lists held items with the reason.

Exported questions should all show 100 percent coverage. If a line is held, use the reason:

| Hold kind | Typical reason text | What to do |
| --- | --- | --- |
| Owner key conflict | `stem asks for N choices but the key has M` | The owner PDF wording and the Correct Answer line disagree. Do not infer the missing letters. Ask the owner to confirm or correct the source. |
| Low OCR | `OCR words below 90` or `overall confidence ... is below 95` | Keep the item held. Do not type guessed words into the stem. A later extract can use a higher resolution page render. |
| Dual OCR disagreement | `OCR passes disagree` | The two passes did not read the same text. Improve the image or the render, then re-run extract. |
| Pixel key not certain | `pixel methods do not agree` or `no text key and no pixel marks` | Two methods must agree, or a text key must map to existing ids. Do not infer a mark from one noisy method. |
| Type ambiguous | `no type rule matched` or `type rules not unique` | Adjust a general rule in `config/question_type_rules.json`, or leave the item for the owner. Never guess the type. |
| Missing or extra words | `missing words:` or `extra words:` | Check extract and alt text. Do not invent captions. Mid-stem words such as "section" or "reference" must stay in the source bag (labels are stripped only as whole lines). |

## How to tune safely

Change values in `config/fidelity.json` and the `fidelity` block of `config/ocr.json` only.

Safer: raise `min_word_confidence` or `min_overall_confidence`; keep `require_100_percent_coverage`, `forbid_extra_words`, `require_unique_type_rule`, `require_certain_key` and `require_pass_agreement` true; keep `allow_answer_not_found` false on this path; keep `min_agreeing_methods` at 2.

Less safe: lowering floors, turning a check off, or accepting a key from one pixel method. That exports unconfirmed text or keys. If you do it, say so in the changelog and re-run real PDFs.

`strip_line_patterns` and `strip_option_prefix` remove only numbering, option letters and label lines from the PDF source bag. Do not add mid-body word deletes for "Section" or "Reference", because those words also appear in real stems.

## Tests

`tests/test_fidelity.py` covers coverage, invented alt, OCR floors, pass agreement, unique type rules, key certainty and the report files.
