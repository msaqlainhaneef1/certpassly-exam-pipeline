# Quality gates

`validate.py` and `check_bank.py` must both exit 0 before a package is offered for a human publish review. The pipeline validate stage exits 1 on any failed check.

Pages stay in draft. A human still has to pass the site's publish gates.

## Always on

- Official facts have a URL, a saved copy, a sha256, and a quote on the saved page.
- If the vendor does not publish a value, the page says "not published by the vendor" (or the equivalent configured phrase). The adapter lists those fields as gaps.
- Simulator time limit and pass mark match the official page, not a cover page on an owner file.
- Questions come only from owner PDFs. Exact types are never merged.
- Keys that were flagged stay unchanged. Items without an answer in the owner file get a key only from a saved official vendor page (verbatim quote, unverified, reviewer needed) or are flagged answer_not_found and excluded from scoring (validate 12l, 12m).
- Banned terms, contact lines and typographic dashes are absent from pages, shared blocks and import files.
- Official vendor brand is present on every page.
- `page_meta_extras.csv` exists.
- Imported questions cite an owner file as `created_source`.
- A delivery partner the vendor names is kept on the exam hub.
- Skipped VCE or other binary files are listed in REVIEW.md.
- Shared blocks are at most the configured share of each page body (default 0.4).
- Duplicate-content shingle check across pages of the same exam.

## Offline

`--offline` or `CERTPASSLY_OFFLINE=1` skips network. The link-check cache and saved sources must already be complete.

## Site-format

The pipeline reads `reference/site-format/v1/` (or the version in `site_format_version`). It never reads application PHP, artisan or a GitHub checkout.
