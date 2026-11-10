# Site format v1

Static snapshot of the CertPassly app contract, bundled so this skill can run without the app repo or GitHub access.

Update later by adding `reference/site-format/v2/` and setting `site_format_version: v2` in config. Do not edit v1 in place once exams have been built against it, unless you are fixing a snapshot error.

Files:

- `question_types.json`: 30 types, aliases, family payload rules, recognition markers
- `csv_templates/`: header-only import templates, column order matches the app workbook contract
- `samples/`: one invented sample row per file, for layout only, not real questions
- `url_routes.json`: lowercase slug and path patterns
- `allowed_statuses.json`: draft-only flags
- `page_fields.json`: page JSON, meta lengths, JSON-LD rules
- `simulator_settings.schema.json`: simulator settings shape
- `import_files.json`: contract CSVs plus sidecar files (including `page_meta_extras.csv`)

A staging dry run (`php artisan certpassly:catalog-workbook-import --mode=dry_run`) is an optional later step for someone who has app access. This pipeline never calls artisan, GitHub or the repo.
