# SEO, meta and schema

Title length: 50 to 60 characters (inclusive), from `pipeline.yaml`.
Meta description: 140 to 160 characters (inclusive).

Every exam has five Google-compliant tables where the facts exist (key facts, skills measured, study plan, FAQ, planned mix). If the vendor does not publish a value, the cell says so. Do not invent a question count or a fixed price.

## JSON-LD

Allowed and required as applicable:

- BreadcrumbList on every page
- EducationalOccupationalCredential on the certification page
- Course on the study-guide page only
- FAQPage on the FAQ page, and only for answers that have an official source

Do not emit Review or Rating. Do not emit Course on the practice-test page.

The application does not have Twitter, og:image or last-checked columns. Put those in the sidecar `page_meta_extras.csv` (listed in site-format `import_files.json`).

## FAQ rich results

FAQ rich results are limited. Only sourced answers go into FAQPage. Unsourced study-advice questions may appear on the page but stay out of the schema.

## URLs

Routes come from `reference/site-format/v1/url_routes.json` and `pipeline.yaml`:

- `/vendors/{vendor}`
- `/certifications/{cert}`
- `/exams/{vendor}/{exam}`
- plus `/objectives`, `/study-guide`, `/faq`, `/practice-test` under the exam

Do not invent a shorter path. A previous pilot used `/microsoft/<exam>` and that is not the live contract.
