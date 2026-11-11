# Lessons learned

Read this before every exam run. Top rules are also repeated in `SKILL.md`. Where a lesson is now a code gate, that is marked. The rest are still human or author-stage rules.

## Re-read the owner rules before each stage (rule)

Brand and denylist rules changed mid-run on the first finished exam. Before catalog, research, author, pages, bank or validate, re-read the latest owner instructions and the live `pipeline.yaml`. Do not rely on a memory of an earlier pass.

## Official vendor brands are required (gate 17c, plus denylist)

Name the official vendor on every page. Seller brands, competitor brands, social networks, phone numbers, emails and "free update" lines are banned. CertPassly is the site brand. The denylist and contact patterns live in `pipeline.yaml` and are applied to owner PDFs, pages, import files and shared blocks.

## Delivery partner: do not drop a partner the vendor still names (gate 17f)

Pearson VUE was removed from draft copy and then had to be restored because it is the official delivery partner named on the vendor's exam pages. If research facts name a delivery partner, the exam hub must keep that name.

## Certification pages must not be thin (rule)

A first certification page that only restated the credential title was rejected. Expand it from sourced official facts: level, path, what the credential covers, and how it relates to the exam. Do not pad it with unsourced marketing.

## Never trust owner-file cover metadata (gate 17)

An owner PDF cover said the exam was 800 / 120 (pass mark / minutes). The official page said 700 / 45. Simulator settings and key-fact tables must use the official page. Record the conflict in `bank_meta.json` (`cover_facts_conflict`) and in REVIEW.md.

## VCE and other binary files are skipped (gate 17b)

`.vce` files are binary. Do not try to parse them as PDFs. List them in intake and in REVIEW.md as skipped.

## Image-only questions need vision and flagging (rule, extractor report)

If the text layer has no stem or only empty option letters, the item is image-keyed. Write a draft from OCR / boxes, then finish it in the author stage with a visual pass. Flag those items. The extractor writes `extracted/unparsed.json` and `image_only` on the item.

## Keys that were flagged are never changed (rule, bank)

If a key is flagged, leave it. Do not "fix" an answer because it looks wrong. Never guess a missing answer. Since v1.1.0 an item with no answer goes to answer_research: a key only from a saved official page with a verbatim quote, flagged unverified; otherwise answer_not_found and excluded from scoring (replaces the old hold rule).

## Questions only from owner PDFs; exact types never merged (gate in check_bank / site-format)

Do not invent items. Do not import from a dump, a blog or a memory. Do not collapse two site types into one (for example, yes/no matrix and multiple-select stay distinct). The 30 types and their aliases live in `reference/site-format/v1/question_types.json`.

## Sheet versus Drive mismatches go to review.csv (rule, catalog)

If the owner sheet and the Drive folder disagree about a file or an exam, write a row in `review.csv`. Do not invent a file or drop one silently.

## Windows PowerShell versus bash (docs)

The owner works in Windows PowerShell. `install.ps1` is the native installer. README commands that use `source` or `./install.sh` are for Linux, macOS or Git Bash. Quote paths with backslashes in PowerShell as needed.

## Zip files sent through chat may not open (docs)

If a zip will not open from a chat download, copy it to the Desktop (or another normal folder) and unzip from there.

## Application columns the site does not have (gate 17d)

The app has no Twitter, og:image or last-checked columns. Write those into the sidecar `page_meta_extras.csv`. Do not fail the import because a core pages table has no such column.

## No Course schema on the practice-test page (gate in validate)

Course JSON-LD belongs on the study-guide page. The practice-test page must not emit Course. FAQPage may only include sourced answers. FAQ rich results are limited.

## No typographic dashes (gate)

Do not use em dashes or en dashes in pages, shared blocks, titles or descriptions. Use a comma, a colon, a hyphen, or "to".

## Budget: batch AI, script everything else (rule)

Research uses a vendor adapter first. AI may fill only official facts the adapter lists as gaps, each with a quote and a source id. The author stage is the one marked AI stage and must be batched (explanations, original page prose, visual transcription where OCR fails, bank_meta). Do not call a model from `run_pipeline.py`.

## What worked on the first finished exam (context)

- `check_bank` passed on the full bank (every built-in check green).
- `validate.py` passed on every then-existing check, and later lesson gates were added on top.
- Stage order that keeps import files stable: pages, then import (emit), then bank (bank appends question rows and does not wipe page sources), then validate (manifest is refreshed after bank).
- Vendor and certification pages built once and skipped when inputs were unchanged.
- Frozen `CERTPASSLY_DATE` made last-updated stamps reproducible.
- Official facts taken from saved, hashed vendor pages, not from seller covers.

A weaker first pilot failed later meta-length checks, used typographic dashes, and used a URL path that is not the live contract. Do not copy that pilot. Use this skill's site-format snapshot and meta ranges.

## Mid-run and future exams (rule)

Nothing in `scripts/` is hardcoded to one exam, one vendor, or one certification slug, except `scripts/adapters/microsoft.py` (the official-page parser for that vendor). New vendors get an adapter module or use `adapters/generic.py`. New exams are selected with `--exam`, `--vendor`, `--all` or `--batch`.


## CI lesson (v1.0.1)

- A clean machine failed because `vision_util.py` imports `cv2` and `numpy` that were never declared. Every third-party import must be listed in `pyproject.toml` and `requirements.txt`. Enforced by the GitHub Actions run on a fresh runner.


## Demo run lessons (v1.0.2)

- A stage that only prints "write this file by hand" is a manual step. Intake now builds `files.json` from the owner folder. If you catch yourself hand-writing pipeline inputs other than the author files and research JSON, that is a defect: fix the script and add a test.
- Do not let a gate pass only because the first exam's author happened to hand-write HTML. Tables are rendered from research rows (check 11b), and the demo test proves it for an exam with plain prose.
- Vendors that do not publish a pass mark are normal. Record the reason in research; pages say "not published by the vendor" and 01c accepts it. Never print a Python `None` on a page.
- (Replaced in v1.1.0) Items with no answer are researched from official pages, never held; never crash on them.
- Never hardcode counts or names from one exam in report text (the "41 image-based items" line).
- Generic official-page parsing must work per block line, with plural units and capitalised labels. Regression tests cover "105 minutes", "Languages: English" and "Name (40-50%)" lines.
- JavaScript-rendered vendor pages (seen on an academy exam page) give an empty plain fetch. Save a rendered copy with its sha256 sidecar or expect every fact to be a gap.
- Windows: assume a legacy code page. The CLI forces UTF-8 mode; tests read and write with `encoding="utf-8"`. Tesseract may be missing from PATH; OCR degrades to "author transcribes".
- CI must show 0 skipped. Optional local-only suites are not collected when their data is absent, instead of being skipped. Real owner extracts never go into Git.

## v1.1.0 lessons (real Data-Con-101 run, AB-730 q089)

- Salesforce exam guides are JavaScript pages: a plain fetch returned 62 text characters. Render with headless Chromium when the text is short; save the rendered HTML, visible text and sha256.
- "Passing score: 70%" has the same shape as an outline line "Solution Positioning: 14%". Fact labels (score, fee, time, minutes) are never domains; weights must sum to about 100.
- "maintainable" matched a renewal regex. Match whole words (renewal, recertification, maintenance) and require a time period or expiry in the sentence.
- Sidecars store absolute paths; a copied workspace must resolve them next to the sidecar, or offline reruns silently miss saved pages.
- A SystemExit with a message must be logged by the runner; "exit 1" alone hid the render-missing reason.
- Bordered answer-area boxes can have one faint (anti-aliased) edge. Accept three dark edges plus the faint one at a lighter threshold (vision_util.boxes) so region coordinates come from the script, not from AI.
- The answer for a no-answer item can come from an official screenshot as well as text (AB-730 q089: the Sources information icon). Save the screenshot with sha256 too, but the verifiable quote must be page text.
- Web search from scripts is often blocked (DuckDuckGo returned 0 results). Always seed answer_research with the exam's official sources and listed URLs; log the failed search.

- Python 3.11 is the oldest supported version: never reuse the outer quote type inside an f-string expression (3.12+ only). Run `py_compile` on 3.11 before pushing. (v1.1.1, CI run 42975699520)
- Path filters must normalise `os.sep` to `/` before matching; Windows CI caught a filter that only worked on Linux. (v1.1.2, CI run 42976175004)
- Paths written into JSON/evidence must be POSIX (`/`), never `os.sep`. (v1.1.3, CI run 42976591708)

## v1.1.4 lessons (Data-Con-101 author through package)

- Official skill weights are not always written as `Name (min-max%)`. Salesforce exam guides use `Name: 14%` when the weight is a single figure. A quote check that only looks for the range form will fail a correct research file. Accept both forms (and an en dash in a range, after normalisation).
- A key-facts helper that is called as `cell('price', '')` will print "not published by the vendor" even when research has a published value. Pass the official value. The same applies to question count: if the vendor publishes a number, the table and simulator settings must use it (`basis=official`). Site choice is only for a gap.
- Validate 12c must follow that rule, or a correct official count would fail the gate.
- Author-stage prose still has to clear word-count and grade gates (150+ words, grade 11 or lower). Short sentences in the study guide dropped the grade from 11.9 to 8.6; vendor and certification pages needed a few more plain sentences to clear 150 words.
- A scripted site-format conformance check can prove that import files match the published contract, including the new researched and answer_not_found fields. It cannot prove that the live site importer accepts those fields until the site team runs their importer.
- Live Drive tests: a public "anyone with the link" folder returns HTTP 200 with `flip-entry` markup and resume works by sha256. A valid-format folder id that is not shared returns HTTP 404 and the script message `drive: folder {id} is not readable (HTTP 404). It must be shared as "Anyone with the link".` Quota and virus-scan HTML pages were not triggered live.

## v1.1.5 lessons (Windows GitHub-install verify)

- `find_saved` remapping sidecar paths is not enough. Any reader that opens `meta['path']` or `meta['text_path']` from a sidecar JSON (`generic._load_sources`, the Microsoft adapter, `validate.py` source walk) must use the same helper. A copied workspace failed research on Windows with "no skill outline with weights" even though the rendered exam-guide HTML and sha256 were present.
- Poppler version matters more than Tesseract for text-layer PDFs. Windows Poppler 25.07.0 `pdftohtml -xml` kept XML document order correct but wrote unusable `top` attributes (collapsed duplicates; some markers near the page max). A global `(page, top, left)` sort then assigned options and "Correct Answer:" to the wrong items and left `answer_raw` empty, so `answer_research` treated almost every item as unanswered. Trust XML order when tops collide or look flipped; keep the Y-sort only when coordinates are consistent, so a same-line letter to the right of "Correct Answer:" still attaches. Normalise CRLF even when a given dump is LF-only.
- Do not check owner-exam `raw.xml` into git. Synthetic pdf2xml fixtures must reproduce the coordinate pathology.


## v1.2.0 lessons (writing brief and the check-then-fix loop, draft)

- Write for people first. Plain English, short sentences, no typographic dashes, and no stock AI phrases. The list lives in `config/banned_ai_phrases.txt` and the brief in `reference/writing-brief.md`. Add a phrase to the data file when a run finds a new one (gate: writing stage).
- A vendor quote may sound formal. It is exempt only when it is found word for word on a saved official page. Never rewrite a quote to dodge the list.
- Search intent comes from research facts, not from guesses. The script never invents a number; an edited intent file with a number that is not in research is flagged.
- Competitor notes are topics only. A run of 8 or more words copied from them fails the writing check, unless the same words are on a saved official page.
- Fix only what is flagged. A part that passed and was rewritten in a fix round is flagged. A second check must run after every fix (validate check 19 when `writing.validate_gate` is true).
- The first run of the long-sentence check found a 41-word sentence in the shared editorial-policy block. Shared blocks are checked once as their own part, so the fix goes to `shared/`, not to every page.
- No writing change may alter a key. The demo `import/questions.csv` sha256 is the same before and after v1.2.0.

## v1.2.0 lessons (real run: Microsoft SC-900 from the owner Drive folder)

- A Drive folder may hold no owner sheet. Build a one-row sheet from the folder name and exam code, and say so in the report. A clean sheet must still write a header-only `review.csv` (it crashed on an empty review list).
- Some owner PDFs put the keyed answer image before an empty "Correct Answer:" line. Promote that image to the answer image instead of treating the item as unanswered (33 SC-900 items).
- Lost ligature glyphs: the text layer can drop fi/fl and leave a gap ("speci c") or no gap at all ("unied"). Gaps are repaired by `text_repair.py`; no-gap words are found by `suspect_lost_ligatures` and fixed by the `textfix` stage. Common words that equal a ligature word minus its ligature ("tracking") are listed under `[known_words]` so they are never flagged.
- Stems and options get spelling, grammar and punctuation fixes only. Never change meaning, the correct answer, or option order. Official vendor product names stay exact. Every change is logged in `text-fixes.json` and gated by the key and option-order identity check (validate 12n).
- Exam length must never come from the extra-time rule ("30 extra minutes"). Discovery must prefer the exam's own page over a generic scoring page, and links with a `#fragment` must be kept.
- DRAG DROP items are `drag_drop` (tiles, targets, pairs), not drop-downs. The marker gate (12f) rightly fails a DRAG DROP item typed as a drop-down.
- A fact the vendor does not publish (languages, format, level) must render as "not published by the vendor", not crash the page build.
- The package zip must never ship raw extracts. `raw.xml` and `cleanups.json` held the removed seller lines verbatim, and `media/src/` held the cover logo. The package stage now leaves them out, ships a redacted cleanups log, and scans every file in the zip (nested archives and camelCase-glued brands too) against the config denylist. Any hit fails the stage. Reports name the file and rule number, never the term.
- Owner keys that current docs contradict are flagged (`key_wrong`, `key_outdated`, `key_arguable`) with a note, never changed. SC-900: 11 flagged.
