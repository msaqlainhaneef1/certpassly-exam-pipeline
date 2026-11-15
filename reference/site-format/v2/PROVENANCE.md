# Site format v2 schema provenance

The file `question.schema.json` in this folder is a verbatim copy of the CertPassly site schema. The pipeline validator uses this copy. The earlier pipeline-only schema (one file per question, with `schema_version`, `meta` and `constraints`) is retired under `retired/question.schema.pipeline-legacy.json` and is not used.

Do not edit `question.schema.json` by hand. To refresh it, copy it again from a read-only site worktree and update the hashes below.

- Site worktree commit: `a3009daa5758a4401ceadd9cf765d8a36bff22bc`
- Schema file last changed in site commit: `13ff486c4bf21c7925ca62dbf0d74a0118325ac6`
- Source path: `reference/site-format/v2/question.schema.json`
- sha256: `da9331c562a0e08cd156cc5efe6181cb8910ec19c523ff83dc43687190dc728e`
- Copied on: 2026-11-15 (Asia/Karachi)

The site checker is `app/Support/SiteFormat/SchemaValidator.php`. Import rules and answer_key shapes live in `app/Services/SiteFormat/SiteFormatImporter.php`, `SiteFormatGrader.php` and `config/site_format.php`. This skill does not change site worktree code.
