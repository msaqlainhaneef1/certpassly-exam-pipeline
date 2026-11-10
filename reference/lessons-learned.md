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

If a key is flagged, leave it. Do not "fix" an answer because it looks wrong. Hold an item that has no usable answer (the first finished bank held one item for a missing answer) instead of guessing.

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
