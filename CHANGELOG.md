# Changelog

## 1.0.1 (2026-11-11)

- Declare numpy, opencv-python-headless and Pillow as dependencies. The extract stage imports them; 1.0.0 wrongly said stdlib only, which failed on clean CI runners.
- Add GitHub Actions test workflow (Linux and Windows, Python 3.11 and 3.13).

## 1.0.0 (2026-11-11)

First packaged release of the CertPassly exam pipeline skill.

- Scripts-first pipeline (`run_pipeline.py` / `certpassly-pipeline`) with one marked AI stage (`author`).
- Versioned site-format snapshot under `reference/site-format/v1/` so the pipeline never reads the site app, artisan or GitHub.
- Vendor adapter pattern (`scripts/adapters/`) chosen from `config/vendors.yaml`, plus a generic official-source parser.
- Shared content blocks (`shared/`) with a configurable page-share cap (default 40 percent).
- Owner PDF extractor with layout detection and an unparsed-item report.
- Lesson gates in `validate.py` (official settings versus cover facts, skipped VCE files, vendor brand, sidecar meta, delivery partner, shared-section share and banned-term checks).
- Offline regression for a finished exam package (when a gold workspace is present) and a non-vendor-specific dry run that reports official-source gaps honestly.
- Git / pip / zip install: `SKILL.md` at repo root, `pyproject.toml` console entry point, `install.sh` and `install.ps1`.
