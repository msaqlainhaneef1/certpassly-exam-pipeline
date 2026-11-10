#!/usr/bin/env bash
# Create a venv, install this skill, check system tools, run the regression tests.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
PY="${PYTHON:-python3}"
if [[ ! -d .venv ]]; then
  echo "Creating virtualenv at $ROOT/.venv"
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install -U pip
pip install -r requirements.txt
pip install -e .
echo
echo "System tools:"
missing=0
for c in pdftohtml pdftoppm pdftotext; do
  if command -v "$c" >/dev/null 2>&1; then
    echo "  ok  $c"
  else
    echo "  MISSING  $c  (poppler)"
    missing=1
  fi
done
if command -v tesseract >/dev/null 2>&1; then
  echo "  ok  tesseract (optional)"
else
  echo "  note  tesseract not found (optional; used for image-only questions)"
fi
if [[ "$missing" -eq 1 ]]; then
  echo
  echo "Install poppler, then re-run this script or add the tools to PATH."
  echo "  Debian / Ubuntu:  sudo apt-get install poppler-utils"
  echo "  macOS (Homebrew): brew install poppler"
  echo "  Windows:          see README (install.ps1)"
fi
echo
echo "Running tests (offline). The full gold-package regression runs only when"
echo "CERTPASSLY_GOLD points at a cached workspace, or when that default path exists."
python -m unittest discover -s tests -v
echo
echo "Installed. Try:  certpassly-pipeline --help"
echo "Full pipeline (needs reference/ and config/):  pip install -e .  or set CERTPASSLY_SKILL_ROOT=$ROOT"
