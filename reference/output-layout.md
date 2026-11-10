# Output layout

All paths are under the workspace root (`--root` or `CERTPASSLY_ROOT`).

```
catalog.csv
review.csv
run.log
config/pipeline.yaml
config/vendors.yaml
research/vendors/<vendor>.json
research/certs/<cert>.json
research/<vendor>/<exam>.json
sources/            (saved official pages, hashed)
cache/linkcheck.json
shared/             (optional workspace overrides; skill seeds are the fallback)
out/<exam>/
  intake/
  extracted/        split.json, layout.json, unparsed.json, items/, raw.xml, cleanups.json
  authoring/        page_prose.json, explanations, bank_meta.json, visual_transcription.json
  media/
  pages/            exam-hub, objectives, study-guide, faq, practice-test
  import/           workbook CSVs, page_meta_extras.csv, simulator_settings.json
  questions.json
  validation.json
  VALIDATION.md
  REVIEW.md
  CLEANUP-LOG.md
  MANIFEST.json
out/vendors/<vendor>/
out/certifications/<cert>/
```

Vendor and certification pages are shared across exams of the same vendor or credential. They are skipped when the input hash is unchanged.

The package zip contains the exam folder plus the shared vendor and certification pages.
