# Test fixtures

## Committed

- `AB-730/authoring/page_prose.json` and `bank_meta.json` : author-stage inputs for the gold-package regression. Seller branding, social links, phone numbers, emails and free-update lines have been stripped. Official vendor names (as they appear on the approved pages) may remain.

- Salesforce / non-Microsoft dry-run inputs are built by the test at runtime (a short synthetic owner PDF and stub research). Nothing from a seller pack is stored here.
- Demo workspaces for both adapter paths are generated at runtime by `tests/demo_kit.py` (synthetic owner PDF with fake seller branding, synthetic official pages, canned author files). No binary fixtures are committed.

## Not committed (gitignored)

Place a gold workspace, if you have one, at one of:

- the path in `CERTPASSLY_GOLD`
- `tests/fixtures/gold/` (gitignored)

A gold workspace is a completed pipeline root with `catalog.csv`, `research/`, `sources/`, `cache/linkcheck.json`, and `out/<exam>/{intake,extracted,authoring,media,pages,questions.json,validation.json}` plus shared vendor and certification pages. Do not copy seller-branded PDFs or Facebook / Innovior / social content into git. If a fixture would still contain that material, keep it outside the repo and point `CERTPASSLY_GOLD` at it.

Without `CERTPASSLY_GOLD` (or `tests/fixtures/gold/`), the gold regression is not collected at all, so CI reports 0 skipped tests.
